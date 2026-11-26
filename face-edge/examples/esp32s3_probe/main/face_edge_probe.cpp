#include <cinttypes>
#include <algorithm>
#include <cstring>
#include <numeric>
#include "dl_image_jpeg.hpp"
#include "human_face_detect.hpp"
#include "human_face_recognition.hpp"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_psram.h"
#include "esp_spiffs.h"
#include "esp_system.h"
#include "esp_timer.h"

extern const uint8_t bill1_start[] asm("_binary_bill1_jpg_start");
extern const uint8_t bill1_end[] asm("_binary_bill1_jpg_end");
extern const uint8_t bill2_start[] asm("_binary_bill2_jpg_start");
extern const uint8_t bill2_end[] asm("_binary_bill2_jpg_end");
extern const uint8_t musk1_start[] asm("_binary_musk1_jpg_start");
extern const uint8_t musk1_end[] asm("_binary_musk1_jpg_end");
extern const uint8_t musk2_start[] asm("_binary_musk2_jpg_start");
extern const uint8_t musk2_end[] asm("_binary_musk2_jpg_end");

static const char *TAG = "face_probe";

static void probe_memory(const char *stage)
{
    ESP_LOGI(TAG, "MEM stage=%s internal_free=%u internal_min_since_boot=%u psram_free=%u psram_largest=%u",
             stage, (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
             (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
             (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM),
             (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM));
}

#if FACE_PROBE_FIXTURE_COMPAT
static void compare_b_landmarks(HumanFaceFeat &model, const dl::image::img_t &image,
                                const std::list<dl::detect::result_t> &faces, bool enroll)
{
    // Approximate points hand-read on the pinned 300x300 JPEGs.
    // ESP-DL order: image-left eye, left mouth, nose, right eye, right mouth.
    static std::vector<float> reference[2];
    const std::vector<int> manual = enroll
        ? std::vector<int>{126,110,127,153,153,134,181,102,180,152}
        : std::vector<int>{107,118,102,173,125,147,158,118,153,171};
    const auto largest = std::max_element(faces.begin(), faces.end(), [](const auto &a, const auto &b) {
        return a.box_area() < b.box_area();
    });
    if (largest->keypoint.size() != 10 || image.width != 300 || image.height != 300) {
        return;
    }
    for (int source = 0; source < 2; ++source) {
        const auto &points = source == 0 ? largest->keypoint : manual;
        const auto *feature = model.run(image, points);
        if (!feature || feature->dtype != dl::DATA_TYPE_FLOAT || !feature->data) {
            continue;
        }
        const auto *data = static_cast<const float *>(feature->data);
        if (enroll) {
            reference[source].assign(data, data + feature->size);
            continue;
        }
        for (int enrollment = 0; enrollment < 2; ++enrollment) {
            if (reference[enrollment].size() == static_cast<size_t>(feature->size)) {
                const float score = std::inner_product(reference[enrollment].begin(),
                                                       reference[enrollment].end(), data, 0.0f);
                ESP_LOGI(TAG, "B_CONTROL enroll=%s query=%s raw_score=%.6f",
                         enrollment ? "manual" : "detector", source ? "manual" : "detector", score);
            }
        }
    }
}
#endif

static bool probe_image(HumanFaceDetect &detector, HumanFaceRecognizer &recognizer,
                        const char *name, const uint8_t *start, const uint8_t *end, bool enroll)
{
    const int64_t begin = esp_timer_get_time();
    dl::image::jpeg_img_t jpeg = {.data = (void *)start, .data_len = (size_t)(end - start)};
    auto image = dl::image::sw_decode_jpeg(jpeg, dl::image::DL_IMAGE_PIX_TYPE_RGB888);
    if (!image.data) {
        ESP_LOGE(TAG, "case=%s decode_failed", name);
        return false;
    }
    const auto *rgb = static_cast<const uint8_t *>(image.data);
    const size_t center = ((image.height / 2) * image.width + image.width / 2) * 3;
    ESP_LOGI(TAG, "IMAGE case=%s width=%d height=%d first_rgb=%u,%u,%u center_rgb=%u,%u,%u",
             name, image.width, image.height, rgb[0], rgb[1], rgb[2],
             rgb[center], rgb[center + 1], rgb[center + 2]);
    const int64_t decoded = esp_timer_get_time();
    auto &faces = detector.run(image);
    const int64_t detected = esp_timer_get_time();
    for (const auto &face : faces) {
        if (face.box.size() == 4) {
            ESP_LOGI(TAG, "DETECTION case=%s score=%.6f box=%d,%d,%d,%d", name, face.score,
                     face.box[0], face.box[1], face.box[2], face.box[3]);
        }
    }
    bool ok = faces.size() == 1;
#if FACE_PROBE_FIXTURE_COMPAT
    if (faces.size() > 1) {
        // Only these embedded upstream JPEGs are used here. Never use this policy for door access.
        ESP_LOGW(TAG, "FIXTURE_COMPAT case=%s face_count=%u policy=upstream_largest_face", name,
                 (unsigned)faces.size());
        ok = true; // HumanFaceRecognizer selects the largest detection, like the upstream example.
    }
#endif
    if (!ok) {
        ESP_LOGW(TAG, "case=%s rejected face_count=%u", name, (unsigned)faces.size());
    } else if (enroll) {
        const esp_err_t err = recognizer.enroll(image, faces);
        ok = err == ESP_OK;
        ESP_LOGI(TAG, "case=%s enrolled=%s template_count=%d", name, esp_err_to_name(err),
                 recognizer.get_num_feats());
    } else {
        const auto results = recognizer.recognize(image, faces);
        ESP_LOGI(TAG, "case=%s match_count=%u (observations only; no access decision)",
                 name, (unsigned)results.size());
        for (const auto &result : results) {
            ESP_LOGI(TAG, "case=%s template_id=%u similarity=%.6f", name, result.id, result.similarity);
        }
    }
    const int64_t finished = esp_timer_get_time();
    ESP_LOGI(TAG, "TIME case=%s decode_us=%" PRId64 " detect_us=%" PRId64
                 " feat_db_us=%" PRId64 " total_us=%" PRId64,
             name, decoded - begin, detected - decoded, finished - detected, finished - begin);
    probe_memory(name);
#if FACE_PROBE_FIXTURE_COMPAT
    if (ok && (start == musk1_start || (start == musk2_start && std::string_view(name) == "query_b"))) {
        compare_b_landmarks(*recognizer.get_feat_model(), image, faces, enroll);
    }
#endif
    heap_caps_free(image.data);
    return ok;
}

static void audit_detector(HumanFaceDetect &detector)
{
    auto a = dl::image::sw_decode_jpeg({(void *)bill1_start, size_t(bill1_end - bill1_start)},
                                      dl::image::DL_IMAGE_PIX_TYPE_RGB888);
    auto b = dl::image::sw_decode_jpeg({(void *)musk1_start, size_t(musk1_end - musk1_start)},
                                      dl::image::DL_IMAGE_PIX_TYPE_RGB888);
    auto *pixels = static_cast<uint8_t *>(heap_caps_malloc(300 * 600 * 3, MALLOC_CAP_SPIRAM));
    if (a.data && b.data && pixels && a.width == 300 && a.height == 300 &&
        b.width == 300 && b.height == 300) {
        auto scene = a;
        scene.data = pixels;
        for (unsigned expected = 0; expected <= 2; ++expected) {
            scene.width = expected == 2 ? 600 : 300;
            for (int row = 0; row < 300; ++row) {
                auto *dst = pixels + row * scene.width * 3;
                if (expected == 0) {
                    std::memset(dst, 128, 900);
                } else {
                    std::memcpy(dst, static_cast<const uint8_t *>(a.data) + row * 900, 900);
                    if (expected == 2) {
                        std::memcpy(dst + 900, static_cast<const uint8_t *>(b.data) + row * 900, 900);
                    }
                }
            }
            const auto &faces = detector.run(scene);
            ESP_LOGI(TAG, "DETECTOR_AUDIT expected=%u actual=%u", expected, (unsigned)faces.size());
            for (const auto &face : faces) {
                if (face.box.size() != 4 || face.keypoint.size() != 10) {
                    ESP_LOGW(TAG, "LANDMARKS expected=%u malformed=1", expected);
                    continue;
                }
                const auto &k = face.keypoint;
                ESP_LOGI(TAG, "LANDMARKS expected=%u score=%.6f box=%d,%d,%d,%d points=%d,%d,%d,%d,%d,%d,%d,%d,%d,%d",
                         expected, face.score, face.box[0], face.box[1], face.box[2], face.box[3],
                         k[0], k[1], k[2], k[3], k[4], k[5], k[6], k[7], k[8], k[9]);
            }
        }
    } else {
        ESP_LOGE(TAG, "DETECTOR_AUDIT fixture_setup_failed");
    }
    heap_caps_free(pixels);
    heap_caps_free(a.data);
    heap_caps_free(b.data);
}

static void face_edge_probe_main()
{
    ESP_LOGI(TAG, "FIXED_JPEG_PROBE idf=%s model=MFN_S8_V1 detector=MSRMNP_S8_V1 no_servo_no_camera",
             esp_get_idf_version());
    ESP_LOGI(TAG, "MODE fixture_compat=%d", FACE_PROBE_FIXTURE_COMPAT);
    ESP_LOGI(TAG, "psram_detected_bytes=%u", (unsigned)esp_psram_get_size());
    if (esp_psram_get_size() == 0) {
        ESP_LOGE(TAG, "PSRAM unavailable; stopping probe");
        return;
    }
    esp_vfs_spiffs_conf_t fs = {};
    fs.base_path = "/probe";
    fs.partition_label = "face_probe_fs";
    fs.max_files = 4;
    fs.format_if_mount_failed = true; // Only this disposable probe partition.
    ESP_ERROR_CHECK(esp_vfs_spiffs_register(&fs));
    probe_memory("before_models");
    {
        HumanFaceDetect detector;
        HumanFaceRecognizer recognizer("/probe/face.db", HumanFaceFeat::MFN_S8_V1);
        ESP_ERROR_CHECK(recognizer.clear_all_feats()); // Reproducible fixture run, not production enrollment.
        bool ok = probe_image(detector, recognizer, "enroll_a", bill1_start, bill1_end, true);
        if (ok) {
            ok = probe_image(detector, recognizer, "query_b_before_enroll", musk2_start, musk2_end, false);
        }
        if (ok) {
            ok = probe_image(detector, recognizer, "enroll_b", musk1_start, musk1_end, true);
        }
        if (ok) {
            ok = probe_image(detector, recognizer, "query_a", bill2_start, bill2_end, false);
        }
        if (ok) {
            ok = probe_image(detector, recognizer, "query_b", musk2_start, musk2_end, false);
        }
        ESP_LOGI(TAG, "PROBE completed=%s (not an accuracy or liveness benchmark)", ok ? "true" : "false");
        audit_detector(detector);
    }
    probe_memory("after_cleanup");
    ESP_ERROR_CHECK(esp_vfs_spiffs_unregister("face_probe_fs"));
}

extern "C" void app_main(void)
{
    face_edge_probe_main();
}
