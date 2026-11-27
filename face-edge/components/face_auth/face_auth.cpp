#include "face_auth.hpp"

#include <cinttypes>
#include <cmath>
#include <cstdio>
#include <new>

#include "dl_image_jpeg.hpp"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "human_face_detect.hpp"
#include "human_face_recognition.hpp"
#include "nvs_flash.h"

namespace face_auth {
namespace {
constexpr char TAG[] = "face_auth";
constexpr size_t kMaxDims = 512;

// NVS keys are limited to 15 characters and card UIDs can be longer, so a key is
// "<48-bit FNV-1a of the subject in hex>s<sample>", e.g. "1a2b3c4d5e6fs0".
void make_key(const char *subject, unsigned sample, char (&key)[16])
{
    uint64_t hash = 1469598103934665603ULL;
    for (const char *p = subject; *p; ++p) {
        hash ^= static_cast<uint8_t>(*p);
        hash *= 1099511628211ULL;
    }
    snprintf(key, sizeof(key), "%012" PRIx64 "s%u", hash & 0xFFFFFFFFFFFFULL, sample);
}

float dot(const float *a, const float *b, size_t n)
{
    float sum = 0.0f;
    for (size_t i = 0; i < n; ++i) {
        sum += a[i] * b[i];
    }
    return sum;
}
} // namespace

const char *to_string(Status status)
{
    switch (status) {
    case Status::Match: return "MATCH";
    case Status::NoMatch: return "NO_MATCH";
    case Status::NoFace: return "NO_FACE";
    case Status::MultipleFaces: return "MULTIPLE_FACES";
    case Status::NotEnrolled: return "NOT_ENROLLED";
    case Status::DecodeError: return "DECODE_ERROR";
    case Status::Error: return "ERROR";
    }
    return "ERROR";
}

FaceAuth::~FaceAuth()
{
    delete detector_;
    delete model_;
    if (store_open_) {
        nvs_close(store_);
    }
}

esp_err_t FaceAuth::begin(const char *partition, const char *ns)
{
    if (ready()) {
        return ESP_OK;
    }
    esp_err_t err = nvs_flash_init_partition(partition);
    if (err != ESP_OK) {
        // Never erase the partition implicitly: it holds the enrolled faces.
        ESP_LOGE(TAG, "init partition %s: %s", partition, esp_err_to_name(err));
        return err;
    }
    err = nvs_open_from_partition(partition, ns, NVS_READWRITE, &store_);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "open %s/%s: %s", partition, ns, esp_err_to_name(err));
        return err;
    }
    store_open_ = true;
    detector_ = new (std::nothrow) HumanFaceDetect();
    model_ = new (std::nothrow) HumanFaceFeat(HumanFaceFeat::MFN_S8_V1);
    if (!ready()) {
        return ESP_ERR_NO_MEM;
    }
    ESP_LOGI(TAG, "ready (partition=%s ns=%s)", partition, ns);
    return ESP_OK;
}

Result FaceAuth::embed(const uint8_t *jpeg, size_t len, const float **embedding)
{
    *embedding = nullptr;
    if (!ready() || !jpeg || !len) {
        return {Status::Error, 0.0f, 0};
    }
    auto image = dl::image::sw_decode_jpeg({const_cast<uint8_t *>(jpeg), len},
                                           dl::image::DL_IMAGE_PIX_TYPE_RGB888);
    if (!image.data) {
        return {Status::DecodeError, 0.0f, 0};
    }
    const auto &faces = detector_->run(image);
    const unsigned count = faces.size();
    if (count > 1) {
        heap_caps_free(image.data);
        return {Status::MultipleFaces, 0.0f, count};
    }
    if (count == 0 || faces.front().keypoint.size() != 10) {
        heap_caps_free(image.data);
        return {Status::NoFace, 0.0f, count};
    }
    const auto *tensor = model_->run(image, faces.front().keypoint);
    heap_caps_free(image.data);
    if (!tensor || tensor->dtype != dl::DATA_TYPE_FLOAT || !tensor->data || tensor->size <= 0 ||
        static_cast<size_t>(tensor->size) > kMaxDims) {
        return {Status::Error, 0.0f, count};
    }
    const auto *values = static_cast<const float *>(tensor->data);
    for (int i = 0; i < tensor->size; ++i) {
        if (!std::isfinite(values[i])) {
            return {Status::Error, 0.0f, count};
        }
    }
    dims_ = tensor->size;
    *embedding = values; // owned by the model, valid until its next run
    return {Status::Match, 0.0f, count};
}

float FaceAuth::best_score(const char *subject, const float *embedding, unsigned *found)
{
    static float stored[kMaxDims]; // single caller task; keeps the 2 KB off the stack
    float best = -2.0f;
    *found = 0;
    for (unsigned sample = 0; sample < kMaxSamples; ++sample) {
        char key[16];
        make_key(subject, sample, key);
        size_t size = dims_ * sizeof(float);
        if (nvs_get_blob(store_, key, stored, &size) != ESP_OK || size != dims_ * sizeof(float)) {
            continue;
        }
        ++*found;
        const float score = dot(stored, embedding, dims_);
        if (score > best) {
            best = score;
        }
    }
    return best;
}

Result FaceAuth::enroll(const uint8_t *jpeg, size_t len, const char *subject, unsigned sample)
{
    if (!subject || !*subject || sample >= kMaxSamples) {
        return {Status::Error, 0.0f, 0};
    }
    const float *embedding = nullptr;
    const Result result = embed(jpeg, len, &embedding);
    if (!embedding) {
        return result;
    }
    char key[16];
    make_key(subject, sample, key);
    esp_err_t err = nvs_set_blob(store_, key, embedding, dims_ * sizeof(float));
    if (err == ESP_OK) {
        err = nvs_commit(store_);
    }
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "store %s: %s", key, esp_err_to_name(err));
        return {Status::Error, 0.0f, result.faces};
    }
    return {Status::Match, 1.0f, result.faces};
}

Result FaceAuth::verify(const uint8_t *jpeg, size_t len, const char *subject, float threshold)
{
    if (!subject || !*subject) {
        return {Status::Error, 0.0f, 0};
    }
    if (sample_count(subject) == 0) {
        return {Status::NotEnrolled, 0.0f, 0};
    }
    const float *embedding = nullptr;
    const Result result = embed(jpeg, len, &embedding);
    if (!embedding) {
        return result;
    }
    unsigned found = 0;
    const float score = best_score(subject, embedding, &found);
    if (!found) {
        return {Status::NotEnrolled, 0.0f, result.faces};
    }
    return {score > threshold ? Status::Match : Status::NoMatch, score, result.faces};
}

Result FaceAuth::identify(const uint8_t *jpeg, size_t len, const char *const *subjects, size_t count,
                          float threshold, size_t *best)
{
    const float *embedding = nullptr;
    const Result result = embed(jpeg, len, &embedding);
    if (!embedding) {
        return result;
    }
    float top = -2.0f;
    size_t top_index = 0;
    unsigned ties = 0;
    bool any = false;
    for (size_t i = 0; i < count; ++i) {
        unsigned found = 0;
        const float score = best_score(subjects[i], embedding, &found);
        if (!found) {
            continue;
        }
        any = true;
        if (score > top) {
            top = score;
            top_index = i;
            ties = 1;
        } else if (score == top) {
            ++ties;
        }
    }
    if (!any) {
        return {Status::NotEnrolled, 0.0f, result.faces};
    }
    if (best) {
        *best = top_index;
    }
    return {(top > threshold && ties == 1) ? Status::Match : Status::NoMatch, top, result.faces};
}

unsigned FaceAuth::sample_count(const char *subject)
{
    if (!store_open_ || !subject) {
        return 0;
    }
    unsigned found = 0;
    for (unsigned sample = 0; sample < kMaxSamples; ++sample) {
        char key[16];
        make_key(subject, sample, key);
        size_t size = 0;
        if (nvs_get_blob(store_, key, nullptr, &size) == ESP_OK) {
            ++found;
        }
    }
    return found;
}

esp_err_t FaceAuth::erase(const char *subject, unsigned first_sample)
{
    if (!store_open_ || !subject) {
        return ESP_ERR_INVALID_STATE;
    }
    for (unsigned sample = first_sample; sample < kMaxSamples; ++sample) {
        char key[16];
        make_key(subject, sample, key);
        const esp_err_t err = nvs_erase_key(store_, key);
        if (err != ESP_OK && err != ESP_ERR_NVS_NOT_FOUND) {
            return err;
        }
    }
    return nvs_commit(store_);
}

} // namespace face_auth
