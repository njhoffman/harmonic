#include "harmonic.hpp"
#include "preset_file.hpp"

#include <SDL3/SDL_opengl.h>

#include <algorithm>
#include <cmath>
#include <stdexcept>

#ifdef HARMONIC_PROJECTM_PLAYBACK
#include <projectM-4/projectM.h>
#endif

namespace harmonic {
bool projectm_playback_available() {
#ifdef HARMONIC_PROJECTM_PLAYBACK
    return true;
#else
    return false;
#endif
}

#ifdef HARMONIC_PROJECTM_PLAYBACK
struct PresetRenderer::Impl {
    const std::vector<float>& audio;
    std::string path, preset_hash;
    std::vector<std::string> textures;
    projectm_handle engine = nullptr;
    GLuint framebuffer = 0, texture = 0;
    int width = 0, height = 0;
    std::size_t cursor = 0, epoch = 0, last_sample = 0;
    std::uint64_t generation = 0, rendered = 0, epoch_frames = 0, reused = 0;
    bool pending_reset = true, cached = false;
    std::string error;

    Impl(const std::vector<float>& pcm, const std::filesystem::path& preset,
         const std::vector<std::string>& texture_paths) : audio(pcm), textures(texture_paths) {
        validate_preset_file(preset);
        if (audio.empty() || audio.size() % channels) throw std::runtime_error("Preset rendering requires stereo PCM");
        path = std::filesystem::absolute(preset).string();
        preset_hash = sha256_file(preset);
        for (auto& directory : textures) {
            if (!std::filesystem::is_directory(directory)) throw std::runtime_error("Texture directory does not exist: " + directory);
            directory = std::filesystem::absolute(directory).string();
        }
    }
    ~Impl() {
        if (engine) projectm_destroy(engine);
        if (framebuffer) glDeleteFramebuffers(1, &framebuffer);
        if (texture) glDeleteTextures(1, &texture);
    }
    void resize(int w, int h) {
        if (w <= 0 || h <= 0) throw std::runtime_error("Invalid preset framebuffer dimensions");
        if (!texture) glGenTextures(1, &texture);
        if (!framebuffer) glGenFramebuffers(1, &framebuffer);
        glActiveTexture(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, texture);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glBindFramebuffer(GL_FRAMEBUFFER, framebuffer);
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0);
        if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE)
            throw std::runtime_error("Could not create preset framebuffer");
        glBindFramebuffer(GL_FRAMEBUFFER, 0);
        width = w; height = h;
        pending_reset = true;
        cached = false;
    }
    static void failed(const char*, const char* message, void* context) {
        static_cast<Impl*>(context)->error = message ? message : "Unknown preset load failure";
    }
    void restart(std::size_t sample) {
        if (engine) { projectm_destroy(engine); engine = nullptr; }
        error.clear();
        cached = false;
        engine = projectm_create();
        if (!engine) throw std::runtime_error("Could not create projectM playback renderer");
        projectm_set_preset_switch_failed_event_callback(engine, failed, this);
        projectm_set_window_size(engine, width, height);
        projectm_set_mesh_size(engine, 64, 48);
        projectm_set_fps(engine, 60);
        projectm_set_preset_locked(engine, true);
        std::vector<const char*> paths;
        for (const auto& directory : textures) paths.push_back(directory.c_str());
        if (!paths.empty()) projectm_set_texture_search_paths(engine, paths.data(), paths.size());
        projectm_set_frame_time(engine, 0);
        projectm_load_preset_file(engine, path.c_str(), false);
        if (!error.empty()) throw std::runtime_error("Preset loading failed: " + error);
        const auto capacity = projectm_pcm_get_max_samples();
        if (!capacity) throw std::runtime_error("projectM returned zero PCM capacity");
        epoch = last_sample = sample;
        cursor = sample > capacity ? sample - capacity : 0;
        epoch_frames = 0;
        ++generation;
        pending_reset = false;
    }
    void draw(double seconds, int w, int h) {
        if (!std::isfinite(seconds)) throw std::runtime_error("Preset time must be finite");
        const auto sample = static_cast<std::size_t>(std::llround(std::clamp(seconds, 0.0,
            static_cast<double>(audio.size() / channels) / sample_rate) * sample_rate));
        if (w != width || h != height) resize(w, h);
        if (pending_reset || sample < last_sample) restart(sample);
        if (!cached || sample != last_sample) {
            if (cached && sample > last_sample) projectm_set_fps(engine,
                std::clamp(static_cast<int>(std::lround(static_cast<double>(sample_rate) / (sample - last_sample))), 1, 240));
            const auto capacity = projectm_pcm_get_max_samples();
            while (cursor < sample) {
                const auto count = static_cast<unsigned>(std::min<std::size_t>(capacity, sample - cursor));
                projectm_pcm_add_float(engine, audio.data() + cursor * channels, count, PROJECTM_STEREO);
                cursor += count;
            }
            projectm_set_frame_time(engine, static_cast<double>(sample - epoch) / sample_rate);
            glDisable(GL_SCISSOR_TEST);
            glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
            projectm_opengl_render_frame_fbo(engine, framebuffer);
            if (!error.empty()) throw std::runtime_error("Preset rendering failed: " + error);
            if (glGetError() != GL_NO_ERROR) throw std::runtime_error("OpenGL error while rendering preset");
            last_sample = sample;
            cached = true;
            ++rendered;
            ++epoch_frames;
        } else ++reused;
        // Copy only the cached preset, never the UI overlay, into the backbuffer.
        // A paused playhead reuses this image without advancing preset feedback.
        glDisable(GL_SCISSOR_TEST);
        glBindFramebuffer(GL_READ_FRAMEBUFFER, framebuffer);
        glReadBuffer(GL_COLOR_ATTACHMENT0);
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0);
        glDrawBuffer(GL_BACK);
        glBlitFramebuffer(0, 0, width, height, 0, 0, width, height, GL_COLOR_BUFFER_BIT, GL_NEAREST);
        glBindFramebuffer(GL_FRAMEBUFFER, 0);
        glReadBuffer(GL_BACK);
        if (glGetError() != GL_NO_ERROR) throw std::runtime_error("OpenGL error while compositing preset");
    }
};

PresetRenderer::PresetRenderer(const std::vector<float>& audio, const std::filesystem::path& preset,
                               const std::vector<std::string>& textures) : impl_(std::make_unique<Impl>(audio, preset, textures)) {}
PresetRenderer::~PresetRenderer() = default;
void PresetRenderer::reset() { impl_->pending_reset = true; }
void PresetRenderer::draw(double seconds, int width, int height) { impl_->draw(seconds, width, height); }
Json::Value PresetRenderer::diagnostics() const {
    Json::Value result;
    result["preset"] = impl_->path;
    result["preset_sha256"] = impl_->preset_hash;
    result["generation"] = Json::UInt64(impl_->generation);
    result["rendered_frames"] = Json::UInt64(impl_->rendered);
    result["frames_since_reset"] = Json::UInt64(impl_->epoch_frames);
    result["cached_frames_reused"] = Json::UInt64(impl_->reused);
    result["sample_index"] = Json::UInt64(impl_->last_sample);
    result["epoch_sample_index"] = Json::UInt64(impl_->epoch);
    result["width"] = impl_->width;
    result["height"] = impl_->height;
    result["shader_fallback_detection"] = false;
    return result;
}
#else
struct PresetRenderer::Impl {};
PresetRenderer::PresetRenderer(const std::vector<float>&, const std::filesystem::path&,
                               const std::vector<std::string>&) {
    throw std::runtime_error("projectM playback is unavailable in this build; explicit frame-time and framebuffer APIs are required");
}
PresetRenderer::~PresetRenderer() = default;
void PresetRenderer::reset() {}
void PresetRenderer::draw(double, int, int) { throw std::runtime_error("projectM playback is unavailable in this build"); }
Json::Value PresetRenderer::diagnostics() const { return Json::Value(Json::objectValue); }
#endif
} // namespace harmonic
