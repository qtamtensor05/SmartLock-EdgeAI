// Standalone UART tool for trying the face model on the board without the lock
// firmware (tools/live_camera*.py). Detection, embedding and storage come from
// the shared face_auth component used by SmartLock itself.
#include <algorithm>
#include <cstdio>
#include <string>
#include "driver/uart.h"
#include "esp_camera.h"
#include "esp_timer.h"
#include "face_auth.hpp"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/base64.h"

namespace {
constexpr unsigned max_people = 32;
constexpr float threshold = 0.5f;
// Separate namespace from the lock (mfn_s8_uid1): numeric IDs, not card UIDs.
constexpr char name_space[] = "mfn_s8_id1";

char subject_names[max_people][4];
const char *subjects[max_people];

esp_err_t init_camera()
{
    // Copy of SmartLock src/config/PinConfig.h, Camera namespace (this tool has
    // no access to the lock headers). Keep both in sync.
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

void process_frame(face_auth::FaceAuth &auth, bool capture_only, unsigned enroll_id, bool report_frame = false)
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
    if (capture_only || report_frame) {
        export_jpeg(*frame);
    }
    if (capture_only) {
        esp_camera_fb_return(frame);
        return;
    }

    face_auth::Result result{};
    size_t best = 0;
    if (enroll_id) {
        result = auth.enroll(frame->buf, frame->len, subjects[enroll_id - 1], 0);
    } else {
        result = auth.identify(frame->buf, frame->len, subjects, max_people, threshold, &best);
    }
    esp_camera_fb_return(frame);

    switch (result.status) {
    case face_auth::Status::NoFace:
    case face_auth::Status::MultipleFaces:
        printf("REJECT face_count=%u\n", result.faces);
        return;
    case face_auth::Status::DecodeError:
        puts("ERR jpeg_decode");
        return;
    case face_auth::Status::Error:
        puts(enroll_id ? "ENROLL status=ERROR" : "ERR embedding");
        return;
    default:
        break;
    }
    if (enroll_id) {
        printf("ENROLL id=%u status=ESP_OK\n", enroll_id);
        return;
    }
    if (result.status == face_auth::Status::Match) {
        printf("MATCH id=%u score=%.6f\n", unsigned(best + 1), result.score);
    } else {
        puts("UNKNOWN");
    }
    printf("TIME total_us=%lld\n", static_cast<long long>(esp_timer_get_time() - started));
}
} // namespace

extern "C" void app_main()
{
    for (unsigned id = 1; id <= max_people; ++id) {
        snprintf(subject_names[id - 1], sizeof(subject_names[0]), "%u", id);
        subjects[id - 1] = subject_names[id - 1];
    }
    static face_auth::FaceAuth auth;
    ESP_ERROR_CHECK(auth.begin("face_live", name_space));
    const auto camera_status = init_camera();
    printf("CAMERA status=%s\n", esp_err_to_name(camera_status));
    if (camera_status != ESP_OK) {
        return;
    }
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
            process_frame(auth, command == "capture", 0);
        } else if (command == "list") {
            for (id = 1; id <= max_people; ++id) {
                if (auth.sample_count(subjects[id - 1])) {
                    printf("PERSON id=%u\n", id);
                }
            }
            puts("LIST_END");
        } else if (sscanf(command.c_str(), "enroll-frame %u %c", &id, &tail) == 1 && id && id <= max_people) {
            process_frame(auth, false, id, true);
        } else if (sscanf(command.c_str(), "enroll %u %c", &id, &tail) == 1 && id && id <= max_people) {
            process_frame(auth, false, id);
        } else if (sscanf(command.c_str(), "delete %u %c", &id, &tail) == 1 && id && id <= max_people) {
            printf("DELETE id=%u status=%s\n", id, esp_err_to_name(auth.erase(subjects[id - 1])));
        } else if (!command.empty()) {
            puts("ERR invalid_command");
        }
        command.clear();
        overflow = false;
    }
}
