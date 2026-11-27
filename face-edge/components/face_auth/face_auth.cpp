#include "face_auth.hpp"

#include <algorithm>
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

dl::image::img_t as_dl_image(void *data, uint16_t width, uint16_t height)
{
    dl::image::img_t image{};
    image.data = data;
    image.width = width;
    image.height = height;
    image.pix_type = dl::image::DL_IMAGE_PIX_TYPE_RGB888;
    return image;
}

// Mean luma and variance of the 4-neighbour Laplacian inside box (RGB888).
void measure(const uint8_t *rgb, int width, const int (&box)[4], float *brightness, float *sharpness)
{
    auto luma = [&](int x, int y) {
        const uint8_t *p = rgb + (static_cast<size_t>(y) * width + x) * 3;
        return (77 * p[0] + 150 * p[1] + 29 * p[2]) >> 8;
    };
    double sum = 0, lap_sum = 0, lap_sq = 0;
    size_t n = 0, m = 0;
    for (int y = box[1]; y <= box[3]; ++y) {
        for (int x = box[0]; x <= box[2]; ++x) {
            const int l = luma(x, y);
            sum += l;
            ++n;
            if (x > box[0] && x < box[2] && y > box[1] && y < box[3]) {
                const int lap = 4 * l - luma(x - 1, y) - luma(x + 1, y) - luma(x, y - 1) - luma(x, y + 1);
                lap_sum += lap;
                lap_sq += static_cast<double>(lap) * lap;
                ++m;
            }
        }
    }
    *brightness = n ? static_cast<float>(sum / n) : 0.0f;
    if (m) {
        const double mean = lap_sum / m;
        *sharpness = static_cast<float>(lap_sq / m - mean * mean);
    } else {
        *sharpness = 0.0f;
    }
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

const char *to_string(Quality quality)
{
    switch (quality) {
    case Quality::Ok: return "OK";
    case Quality::DecodeError: return "DECODE_ERROR";
    case Quality::NoFace: return "NO_FACE";
    case Quality::MultipleFaces: return "MULTIPLE_FACES";
    case Quality::TooSmall: return "TOO_SMALL";
    case Quality::TooLarge: return "TOO_LARGE";
    case Quality::OffCenter: return "OFF_CENTER";
    case Quality::TooDark: return "TOO_DARK";
    case Quality::TooBright: return "TOO_BRIGHT";
    case Quality::Blurry: return "BLURRY";
    }
    return "ERROR";
}

FaceAuth::~FaceAuth()
{
    drop_inspected();
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

void FaceAuth::drop_inspected()
{
    if (cached_.data) {
        heap_caps_free(cached_.data);
    }
    cached_ = Image{};
    cached_keypoint_.clear();
}

Inspection FaceAuth::inspect(const uint8_t *jpeg, size_t len, const QualityLimits &limits)
{
    drop_inspected();
    Inspection out{Quality::DecodeError, 0, {0, 0, 0, 0}, 0.0f, 0.0f};
    if (!ready() || !jpeg || !len) {
        return out;
    }
    auto image = dl::image::sw_decode_jpeg({const_cast<uint8_t *>(jpeg), len},
                                           dl::image::DL_IMAGE_PIX_TYPE_RGB888);
    if (!image.data) {
        return out;
    }
    const auto &faces = detector_->run(image);
    out.faces = faces.size();
    if (out.faces != 1 || faces.front().keypoint.size() != 10 || faces.front().box.size() != 4) {
        out.quality = out.faces > 1 ? Quality::MultipleFaces : Quality::NoFace;
        heap_caps_free(image.data);
        return out;
    }

    const auto &face = faces.front();
    const int w = image.width, h = image.height;
    for (int i = 0; i < 4; ++i) {
        out.box[i] = std::clamp(face.box[i], 0, (i % 2 ? h : w) - 1);
    }
    measure(static_cast<const uint8_t *>(image.data), w, out.box, &out.brightness, &out.sharpness);

    const int face_w = out.box[2] - out.box[0];
    const float cx = (out.box[0] + out.box[2]) * 0.5f / w - 0.5f;
    const float cy = (out.box[1] + out.box[3]) * 0.5f / h - 0.5f;
    const bool touches_edge = out.box[0] < limits.edge_margin_px || out.box[1] < limits.edge_margin_px ||
                              out.box[2] > w - 1 - limits.edge_margin_px || out.box[3] > h - 1 - limits.edge_margin_px;

    if (face_w < limits.min_face_px) {
        out.quality = Quality::TooSmall;
    } else if (face_w > limits.max_face_px) {
        out.quality = Quality::TooLarge;
    } else if (touches_edge || std::fabs(cx) > limits.max_center_offset || std::fabs(cy) > limits.max_center_offset) {
        out.quality = Quality::OffCenter;
    } else if (out.brightness < limits.min_brightness) {
        out.quality = Quality::TooDark;
    } else if (out.brightness > limits.max_brightness) {
        out.quality = Quality::TooBright;
    } else if (out.sharpness < limits.min_sharpness) {
        out.quality = Quality::Blurry;
    } else {
        out.quality = Quality::Ok;
    }

    if (out.quality == Quality::Ok) {
        cached_.data = image.data; // kept for enroll_inspected()/verify_inspected()
        cached_.width = image.width;
        cached_.height = image.height;
        cached_keypoint_ = face.keypoint;
    } else {
        heap_caps_free(image.data);
    }
    return out;
}

Result FaceAuth::embed_image(const Image &image, const std::vector<int> &keypoint, unsigned faces,
                             const float **embedding)
{
    *embedding = nullptr;
    auto dl_image = as_dl_image(image.data, image.width, image.height);
    const auto *tensor = model_->run(dl_image, keypoint);
    if (!tensor || tensor->dtype != dl::DATA_TYPE_FLOAT || !tensor->data || tensor->size <= 0 ||
        static_cast<size_t>(tensor->size) > kMaxDims) {
        return {Status::Error, 0.0f, faces};
    }
    const auto *values = static_cast<const float *>(tensor->data);
    for (int i = 0; i < tensor->size; ++i) {
        if (!std::isfinite(values[i])) {
            return {Status::Error, 0.0f, faces};
        }
    }
    dims_ = tensor->size;
    *embedding = values; // owned by the model, valid until its next run
    return {Status::Match, 0.0f, faces};
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
    const Image owned{image.data, image.width, image.height};
    const Result result = embed_image(owned, faces.front().keypoint, count, embedding);
    heap_caps_free(image.data);
    return result;
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

Result FaceAuth::store_sample(const char *subject, unsigned sample, const float *embedding, unsigned faces)
{
    char key[16];
    make_key(subject, sample, key);
    esp_err_t err = nvs_set_blob(store_, key, embedding, dims_ * sizeof(float));
    if (err == ESP_OK) {
        err = nvs_commit(store_);
    }
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "store %s: %s", key, esp_err_to_name(err));
        return {Status::Error, 0.0f, faces};
    }
    return {Status::Match, 1.0f, faces};
}

Result FaceAuth::compare(const char *subject, float threshold, const float *embedding, unsigned faces)
{
    unsigned found = 0;
    const float score = best_score(subject, embedding, &found);
    if (!found) {
        return {Status::NotEnrolled, 0.0f, faces};
    }
    return {score > threshold ? Status::Match : Status::NoMatch, score, faces};
}

Result FaceAuth::enroll_inspected(const char *subject, unsigned sample)
{
    if (!subject || !*subject || sample >= kMaxSamples || !has_inspected()) {
        return {Status::Error, 0.0f, 0};
    }
    const float *embedding = nullptr;
    const Result result = embed_image(cached_, cached_keypoint_, 1, &embedding);
    drop_inspected();
    return embedding ? store_sample(subject, sample, embedding, 1) : result;
}

Result FaceAuth::verify_inspected(const char *subject, float threshold)
{
    if (!subject || !*subject || !has_inspected()) {
        return {Status::Error, 0.0f, 0};
    }
    if (sample_count(subject) == 0) {
        drop_inspected();
        return {Status::NotEnrolled, 0.0f, 1};
    }
    const float *embedding = nullptr;
    const Result result = embed_image(cached_, cached_keypoint_, 1, &embedding);
    drop_inspected();
    return embedding ? compare(subject, threshold, embedding, 1) : result;
}

Result FaceAuth::enroll(const uint8_t *jpeg, size_t len, const char *subject, unsigned sample)
{
    if (!subject || !*subject || sample >= kMaxSamples) {
        return {Status::Error, 0.0f, 0};
    }
    const float *embedding = nullptr;
    const Result result = embed(jpeg, len, &embedding);
    return embedding ? store_sample(subject, sample, embedding, result.faces) : result;
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
    return embedding ? compare(subject, threshold, embedding, result.faces) : result;
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
