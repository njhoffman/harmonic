#pragma once

#include <SDL3/SDL.h>
#include <json/json.h>

#include <cstdint>
#include <filesystem>
#include <memory>
#include <string>
#include <vector>

namespace harmonic {

inline constexpr int sample_rate = 48000;
inline constexpr int channels = 2;

std::string sha256(const void* data, std::size_t bytes);
std::string sha256_file(const std::filesystem::path& path);
std::vector<float> decode_audio(const std::filesystem::path& path);

struct Bundle {
    Json::Value manifest;
    std::filesystem::path audio_path;
    std::int64_t sample_count = 0;
    int hop = 0;
    int bands = 0;
    float rms_scale = 1;
    float onset_scale = 1;
    float spectrum_top_db = -10;
    std::vector<float> rms, peak, onset, spectrum;
    std::vector<float> band_edges;

    double duration() const { return static_cast<double>(sample_count) / sample_rate; }
    float interpolate(const std::vector<float>& values, double seconds) const;
    std::vector<float> spectrum_at(double seconds) const;
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

void compositor_check(Renderer& renderer, PresetRenderer& preset, const Bundle& bundle,
                      double start, const std::filesystem::path& output);

} // namespace harmonic
