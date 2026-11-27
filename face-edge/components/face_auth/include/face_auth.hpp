#pragma once

#include <cstddef>
#include <cstdint>

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
    Result embed(const uint8_t *jpeg, size_t len, const float **embedding);
    float best_score(const char *subject, const float *embedding, unsigned *found);

    HumanFaceDetect *detector_ = nullptr;
    HumanFaceFeat *model_ = nullptr;
    nvs_handle_t store_ = 0;
    bool store_open_ = false;
    size_t dims_ = 0;
};

} // namespace face_auth
