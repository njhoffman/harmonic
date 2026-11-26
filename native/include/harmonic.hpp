#pragma once

#include <SDL3/SDL.h>
#include <json/json.h>

#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace harmonic {

inline constexpr int sample_rate = 48000;
inline constexpr int channels = 2;
inline constexpr double max_offset_seconds = 2.0;

std::string sha256(const void* data, std::size_t bytes);
std::string sha256_file(const std::filesystem::path& path);
std::vector<float> decode_audio(const std::filesystem::path& path);

struct FeatureStream {
    std::string name = "mix", target, role = "mix";
    std::int64_t start_sample = 0;
    std::int64_t sample_count = 0;
    int hop = 0;
    int bands = 0;
    float rms_scale = 1;
    float onset_scale = 1;
    float spectrum_top_db = -10;
    std::vector<float> rms, peak, onset, spectrum;
    bool covers(double seconds) const;
    float interpolate(const std::vector<float>& values, double seconds) const;
    std::vector<float> spectrum_at(double seconds) const;
};

// Per-frame prompt presence probabilities (schema 3). Frame i covers the half-open
// interval [start + i*frame_samples, start + (i+1)*frame_samples). No threshold
// is applied in the bundle; reliability records how the prompt was benchmarked.
struct PresenceStream {
    std::string target, prompt, reliability;
    std::int64_t start_sample = 0;
    std::int64_t sample_count = 0;
    int frame_samples = 0;
    std::vector<float> probability;
    bool covers(double seconds) const;
    float at(double seconds) const;
};

struct Bundle : FeatureStream {
    Json::Value manifest;
    std::filesystem::path audio_path;
    std::vector<float> band_edges;
    std::vector<FeatureStream> sources;
    std::vector<PresenceStream> presence;  // Empty: presence unknown (older results), not absent.
    const PresenceStream* presence_for(const std::string& target) const;
    double duration() const { return static_cast<double>(sample_count) / sample_rate; }
};

Bundle load_bundle(const std::filesystem::path& path, const std::filesystem::path& audio_override = {});

// Owns a single SDL audio stream. All source cursors are on the decoded 48 kHz
// timeline. SDL's stream lock serializes the callback and transport operations.
class Transport {
public:
    explicit Transport(const std::vector<float>& audio);
    ~Transport();
    Transport(const Transport&) = delete;
    Transport& operator=(const Transport&) = delete;
    void resume();
    void pause();
    void seek(double seconds);
    bool paused() const { return paused_; }
    double position();
    double duration() const { return static_cast<double>(audio_.size() / channels) / sample_rate; }
    double buffer_seconds() const { return buffer_seconds_; }
    // "<SDL audio driver>/<output device name>": the key for saved calibration.
    std::string device_key() const;
    // Frames written to the SDL stream that the device has not consumed yet.
    std::int64_t queued_frames();
    std::string error();

private:
    static void SDLCALL callback(void* userdata, SDL_AudioStream* stream, int additional, int total);
    double position_locked();
    void reset_locked(double frame);
    const std::vector<float>& audio_;
    SDL_AudioStream* stream_ = nullptr;
    std::size_t cursor_ = 0;
    double anchor_frame_ = 0, held_frame_ = 0, last_frame_ = 0, seek_floor_ = 0;
    Uint64 anchor_ticks_ = 0;
    double buffer_seconds_ = 0;
    bool paused_ = true, flushed_ = false;
    std::string callback_error_;
};

class Renderer {
public:
    Renderer(int width, int height, bool hidden);
    ~Renderer();
    Renderer(const Renderer&) = delete;
    Renderer& operator=(const Renderer&) = delete;
    SDL_Window* window() const { return window_; }
    void set_residuals(bool value) { residuals_ = value; }
    // Shown after the offset readout: where the current offset came from.
    void set_offset_label(std::string value) { offset_label_ = std::move(value); }
    enum class View { graphs, combined, preset };
    void draw(const Bundle& bundle, double seconds, bool paused, double offset, bool relative,
              View view = View::graphs);
    void screenshot(const std::filesystem::path& path);
    std::string frame_checksum();
    // Coordinates below are logical window coordinates, unaffected by display DPI.
    static constexpr float timeline_left = 42, timeline_top = 470;

private:
    struct Vertex { float x, y, r, g, b, a; };
    void rect(float x, float y, float w, float h, float r, float g, float b, float a = 1);
    void text(float x, float y, const std::string& value, float scale, float r, float g, float b);
    SDL_Window* window_ = nullptr;
    SDL_GLContext context_ = nullptr;
    unsigned int program_ = 0, vao_ = 0, vbo_ = 0;
    int resolution_ = -1;
    bool residuals_ = false;
    std::string offset_label_;
    std::vector<Vertex> vertices_;
};

bool projectm_playback_available();

// Owns preset feedback separately from the UI. Its GL resources must be destroyed
// before the Renderer/context. PCM and animation follow the same sample clock.
class PresetRenderer {
public:
    PresetRenderer(const std::vector<float>& audio, const std::filesystem::path& preset,
                   const std::vector<std::string>& textures = {});
    ~PresetRenderer();
    PresetRenderer(const PresetRenderer&) = delete;
    PresetRenderer& operator=(const PresetRenderer&) = delete;
    void reset();
    void draw(double seconds, int width, int height);
    Json::Value diagnostics() const;
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

// Per-output-device feature offsets saved from the player (S key). The file is
// $XDG_CONFIG_HOME/harmonic/calibration.json (default ~/.config). A file that
// cannot be parsed is reported in `error`, never applied, and never overwritten.
struct Calibration {
    std::filesystem::path path;
    std::optional<double> offset_ms;
    std::string error;
};
std::filesystem::path calibration_path();
Calibration load_calibration(const std::filesystem::path& path, const std::string& device);
void save_calibration(const std::filesystem::path& path, const std::string& device, double offset_ms);

// Records per-frame CPU, swap, and GPU timing plus scripted seeks for a
// --frame-report. GPU time uses GL_TIMESTAMP pairs, which cannot conflict with
// queries projectM issues; results are read a few frames later to avoid stalls.
class FrameTimer {
public:
    FrameTimer();
    ~FrameTimer();
    FrameTimer(const FrameTimer&) = delete;
    FrameTimer& operator=(const FrameTimer&) = delete;
    void begin(Uint64 now, double position, std::int64_t queued_frames);
    void drawn(Uint64 now);
    void swapped(Uint64 now);
    void seek(Uint64 requested, Uint64 returned, double from, double to);
    // Writes the report; context supplies display, audio, and scenario details.
    void write(const std::filesystem::path& path, Json::Value context);
private:
    static constexpr int ring = 8;
    void collect(bool wait);
    struct Pending { std::size_t frame; bool active; };
    unsigned int queries_[ring * 2] = {};
    Pending pending_[ring] = {};
    std::size_t next_query_ = 0;
    std::vector<Uint64> begin_ns_, draw_ns_, swap_ns_;
    std::vector<double> position_, gpu_ns_;
    std::vector<std::int64_t> queued_;
    Json::Value seeks_{Json::arrayValue};
    int settling_ = -1, presenting_ = -1;
    Uint64 origin_ = 0;
};

void compositor_check(Renderer& renderer, PresetRenderer& preset, const Bundle& bundle,
                      double start, const std::filesystem::path& output);

} // namespace harmonic
