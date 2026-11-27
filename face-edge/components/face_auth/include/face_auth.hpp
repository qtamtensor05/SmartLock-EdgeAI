#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

#include "esp_err.h"
#include "nvs.h"

class HumanFaceDetect;
class HumanFaceFeat;

namespace face_auth {

enum class Status : uint8_t {
    Match,         // best stored sample scored above the threshold (enroll: sample stored)
    NoMatch,       // a single face was found but did not match
    NoFace,        // detector found no face (or landmarks were incomplete)
    MultipleFaces, // more than one face in the frame: always rejected
    NotEnrolled,   // no stored sample for this subject
    DecodeError,   // the JPEG could not be decoded
    Error,         // model, embedding or storage failure
};

const char *to_string(Status status);

struct Result {
    Status status;
    float score;    // best cosine similarity, or 0 when nothing was compared
    unsigned faces; // faces reported by the detector
};

// Why a frame is (not) good enough to be captured. Checked in this order.
enum class Quality : uint8_t {
    Ok,
    DecodeError,
    NoFace,
    MultipleFaces,
    TooSmall,  // face too far: move closer
    TooLarge,  // face too close: move back
    OffCenter, // face cut by the frame edge or far from the centre
    TooDark,
    TooBright,
    Blurry,
};

const char *to_string(Quality quality);

// Limits for a 320x240 frame; the firmware may override them.
struct QualityLimits {
    int min_face_px = 70;            // face box width
    int max_face_px = 200;
    int edge_margin_px = 4;          // box must not touch the frame edge
    float max_center_offset = 0.25f; // |face centre - frame centre| / frame size
    float min_brightness = 60.0f;    // mean luma inside the face box, 0..255
    float max_brightness = 210.0f;
    float min_sharpness = 20.0f;     // variance of the Laplacian inside the face box
};

struct Inspection {
    Quality quality;
    unsigned faces;
    int box[4];       // x1, y1, x2, y2 of the face (valid when faces == 1)
    float brightness; // valid when faces == 1
    float sharpness;  // valid when faces == 1
};

// Detects one face in a JPEG frame, computes its MFN embedding and compares it
// with embeddings stored in an NVS partition. The caller owns the camera and
// passes the JPEG of a fresh frame; this class never touches GPIOs or the lock.
class FaceAuth {
public:
    static constexpr unsigned kMaxSamples = 5;

    FaceAuth() = default;
    ~FaceAuth();
    FaceAuth(const FaceAuth &) = delete;
    FaceAuth &operator=(const FaceAuth &) = delete;

    // Loads the models and opens <partition>/<ns>. The namespace carries the
    // model/schema version: embeddings from another model must not be mixed.
    esp_err_t begin(const char *partition = "face_live", const char *ns = "mfn_s8_uid1");
    bool ready() const { return detector_ != nullptr && model_ != nullptr && store_open_; }

    // Decode + detect only, and rate the frame. When the result is Ok the decoded
    // image and landmarks are kept, so enroll_inspected()/verify_inspected() can
    // embed exactly this frame without running the detector again.
    Inspection inspect(const uint8_t *jpeg, size_t len, const QualityLimits &limits);
    bool has_inspected() const { return cached_.data != nullptr; }
    void drop_inspected();
    Result enroll_inspected(const char *subject, unsigned sample);
    Result verify_inspected(const char *subject, float threshold);

    // Full pipeline on one JPEG (manual capture).
    // Stores sample `sample` (0-based, < kMaxSamples) for `subject` (e.g. a card UID).
    Result enroll(const uint8_t *jpeg, size_t len, const char *subject, unsigned sample);
    // 1:1 verification of `subject` against all of its stored samples.
    Result verify(const uint8_t *jpeg, size_t len, const char *subject, float threshold);
    // 1:N identification. On Match, *best is the index into `subjects`.
    Result identify(const uint8_t *jpeg, size_t len, const char *const *subjects, size_t count,
                    float threshold, size_t *best);

    unsigned sample_count(const char *subject);
    // Removes the samples of `subject` with index >= first_sample (all by default).
    esp_err_t erase(const char *subject, unsigned first_sample = 0);

private:
    struct Image {
        void *data = nullptr;
        uint16_t width = 0;
        uint16_t height = 0;
    };

    Result embed(const uint8_t *jpeg, size_t len, const float **embedding);
    Result embed_image(const Image &image, const std::vector<int> &keypoint, unsigned faces,
                       const float **embedding);
    Result store_sample(const char *subject, unsigned sample, const float *embedding, unsigned faces);
    Result compare(const char *subject, float threshold, const float *embedding, unsigned faces);
    float best_score(const char *subject, const float *embedding, unsigned *found);

    HumanFaceDetect *detector_ = nullptr;
    HumanFaceFeat *model_ = nullptr;
    nvs_handle_t store_ = 0;
    bool store_open_ = false;
    size_t dims_ = 0;
    Image cached_;
    std::vector<int> cached_keypoint_;
};

} // namespace face_auth
