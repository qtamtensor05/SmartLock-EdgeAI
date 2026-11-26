#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>
#include <numeric>
#include <string>
#include <vector>
#include "dl_image_jpeg.hpp"
#include "driver/uart.h"
#include "esp_camera.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "human_face_detect.hpp"
#include "human_face_recognition.hpp"
#include "mbedtls/base64.h"
#include "nvs_flash.h"

namespace {
constexpr unsigned max_people = 32;
constexpr float threshold = 0.5f;
constexpr char partition[] = "face_live";

esp_err_t init_camera()
{
    // SmartLock src/config/PinConfig.h, Camera namespace.
    camera_config_t config{};
    config.pin_pwdn = -1;
    config.pin_reset = -1;
    config.pin_xclk = 15;
    config.pin_sccb_sda = 4;
    config.pin_sccb_scl = 5;
    config.pin_d0 = 11;
    config.pin_d1 = 9;
    config.pin_d2 = 8;
    config.pin_d3 = 10;
    config.pin_d4 = 12;
    config.pin_d5 = 18;
    config.pin_d6 = 17;
    config.pin_d7 = 16;
    config.pin_vsync = 6;
    config.pin_href = 7;
    config.pin_pclk = 13;
    config.xclk_freq_hz = 20000000;
    config.ledc_timer = LEDC_TIMER_0;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 12;
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
    return esp_camera_init(&config);
}

void export_jpeg(const camera_fb_t &frame)
{
    printf("JPEG_BEGIN %u\n", unsigned(frame.len));
    for (size_t offset = 0; offset < frame.len; offset += 192) {
        unsigned char encoded[257];
        size_t written = 0;
        const size_t count = std::min(size_t(192), frame.len - offset);
        if (mbedtls_base64_encode(encoded, sizeof(encoded), &written, frame.buf + offset, count) != 0) {
            puts("ERR jpeg_encoding");
            return;
        }
        printf("%.*s\n", int(written), reinterpret_cast<const char *>(encoded));
    }
    puts("JPEG_END");
}

void process_frame(nvs_handle_t store, HumanFaceDetect &detector, HumanFaceFeat &model,
                   bool capture_only, unsigned enroll_id, bool report_frame = false)
{
    const int64_t started = esp_timer_get_time();
    auto *frame = esp_camera_fb_get();
    if (frame && !capture_only) {
        // With a single framebuffer, the first JPEG may predate the command.
        esp_camera_fb_return(frame);
        frame = esp_camera_fb_get();
    }
    if (!frame) {
        puts("ERR camera_capture");
        return;
    }
    if (capture_only) {
        export_jpeg(*frame);
        esp_camera_fb_return(frame);
        return;
    }
    auto image = dl::image::sw_decode_jpeg({frame->buf, frame->len}, dl::image::DL_IMAGE_PIX_TYPE_RGB888);
    if (report_frame) {
        export_jpeg(*frame);
    }
    esp_camera_fb_return(frame);
    if (!image.data) {
        puts("ERR jpeg_decode");
        return;
    }
    const auto &faces = detector.run(image);
    if (faces.size() != 1 || faces.front().keypoint.size() != 10) {
        printf("REJECT face_count=%u\n", unsigned(faces.size()));
        heap_caps_free(image.data);
        return;
    }
    const auto *embedding = model.run(image, faces.front().keypoint);
    heap_caps_free(image.data);
    if (!embedding || embedding->dtype != dl::DATA_TYPE_FLOAT || !embedding->data || embedding->size <= 0) {
        puts("ERR embedding");
        return;
    }
    const auto *feature = static_cast<const float *>(embedding->data);
    const size_t count = embedding->size;
    const size_t bytes = count * sizeof(float);
    if (!std::all_of(feature, feature + count, [](float value) { return std::isfinite(value); })) {
        puts("ERR nonfinite_embedding");
        return;
    }
    if (enroll_id) {
        const auto key = std::to_string(enroll_id);
        auto err = nvs_set_blob(store, key.c_str(), feature, bytes);
        if (err == ESP_OK) {
            err = nvs_commit(store);
        }
        printf("ENROLL id=%u status=%s\n", enroll_id, esp_err_to_name(err));
        return;
    }
    std::vector<float> candidate(count);
    float best = -std::numeric_limits<float>::infinity();
    unsigned best_id = 0;
    unsigned ties = 0;
    for (unsigned id = 1; id <= max_people; ++id) {
        size_t size = bytes;
        if (nvs_get_blob(store, std::to_string(id).c_str(), candidate.data(), &size) != ESP_OK || size != bytes) {
            continue;
        }
        const float score = std::inner_product(candidate.begin(), candidate.end(), feature, 0.0f);
        if (score > best) {
            best = score;
            best_id = id;
            ties = 1;
        } else if (score == best) {
            ++ties;
        }
    }
    if (best_id && best > threshold && ties == 1) {
        printf("MATCH id=%u score=%.6f\n", best_id, best);
    } else {
        puts("UNKNOWN");
    }
    printf("TIME total_us=%lld\n", static_cast<long long>(esp_timer_get_time() - started));
}
}

extern "C" void app_main()
{
    ESP_ERROR_CHECK(nvs_flash_init_partition(partition));
    nvs_handle_t store;
    ESP_ERROR_CHECK(nvs_open_from_partition(partition, "mfn_s8_v1", NVS_READWRITE, &store));
    const auto camera_status = init_camera();
    printf("CAMERA status=%s\n", esp_err_to_name(camera_status));
    if (camera_status != ESP_OK) {
        nvs_close(store);
        return;
    }
    HumanFaceDetect detector;
    HumanFaceFeat model(HumanFaceFeat::MFN_S8_V1);
    // Leave the boot log at 115200 and switch the application console for JPEG transfer.
    fflush(stdout);
    ESP_ERROR_CHECK(uart_wait_tx_idle_polling(UART_NUM_0));
    ESP_ERROR_CHECK(uart_set_baudrate(UART_NUM_0, 460800));
    puts("READY: capture | enroll ID | identify | list | delete ID (ID 1..32)");
    std::string command;
    bool overflow = false;
    for (;;) {
        const int ch = getchar();
        if (ch == EOF) {
            clearerr(stdin);
            vTaskDelay(pdMS_TO_TICKS(20));
            continue;
        }
        if (ch != '\n' && ch != '\r') {
            if (command.size() < 63) {
                command.push_back(static_cast<char>(ch));
            } else {
                overflow = true;
            }
            continue;
        }
        unsigned id = 0;
        char tail = 0;
        if (overflow) {
            puts("ERR command_too_long");
        } else if (command == "capture" || command == "identify") {
            process_frame(store, detector, model, command == "capture", 0);
        } else if (command == "list") {
            for (id = 1; id <= max_people; ++id) {
                size_t size = 0;
                if (nvs_get_blob(store, std::to_string(id).c_str(), nullptr, &size) == ESP_OK) {
                    printf("PERSON id=%u\n", id);
                }
            }
            puts("LIST_END");
        } else if (sscanf(command.c_str(), "enroll-frame %u %c", &id, &tail) == 1 && id && id <= max_people) {
            process_frame(store, detector, model, false, id, true);
        } else if (sscanf(command.c_str(), "enroll %u %c", &id, &tail) == 1 && id && id <= max_people) {
            process_frame(store, detector, model, false, id);
        } else if (sscanf(command.c_str(), "delete %u %c", &id, &tail) == 1 && id && id <= max_people) {
            auto err = nvs_erase_key(store, std::to_string(id).c_str());
            if (err == ESP_OK) {
                err = nvs_commit(store);
            }
            printf("DELETE id=%u status=%s\n", id, esp_err_to_name(err));
        } else if (!command.empty()) {
            puts("ERR invalid_command");
        }
        command.clear();
        overflow = false;
    }
}
