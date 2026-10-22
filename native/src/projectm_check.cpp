#include "harmonic.hpp"
#include "terminal.hpp"

#include <SDL3/SDL_opengl.h>
#include <projectM-4/projectM.h>

#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <numeric>
#include <stdexcept>

namespace {
constexpr int fps = 60;
struct Options {
    std::filesystem::path bundle, preset, output;
    std::vector<std::string> textures;
    int frames = 180, width = 1920, height = 1080;
    double start = 0;
    bool help = false, version = false;
};
void usage() {
    std::cout << "Usage: harmonic-projectm-check BUNDLE_OR_MANIFEST --preset FILE --output DIRECTORY [options]\n"
        "  -h, --help          Show usage\n"
        "  -v, --version       Print the checker version\n"
        "  --preset FILE       Local MilkDrop preset to verify\n"
        "  --output DIRECTORY  New directory for preview.ppm and report.json\n"
        "  --textures PATH     Texture search directory (repeatable)\n"
        "  --start SECONDS     Original-mix excerpt position (default: 0)\n"
        "  --frames NUMBER     Frames to render at a 60 Hz timeline (default: 180)\n"
        "  --width NUMBER      Output width, 920..8192 (default: 1920)\n"
        "  --height NUMBER     Output height, 720..8192 (default: 1080)\n"
        "\nUses an offscreen OpenGL context without audio output. Saves renderer identity,\n"
        "preset/audio checksums, PCM counts, and completed-render timings.\n";
}
double number(const std::string& text) {
    std::size_t end = 0;
    const double value = std::stod(text, &end);
    if (end != text.size() || !std::isfinite(value)) throw std::runtime_error("Invalid number: " + text);
    return value;
}
int integer(const std::string& text, int low, int high) {
    const double value = number(text);
    if (value != std::floor(value) || value < low || value > high)
        throw std::runtime_error("Expected an integer in " + std::to_string(low) + ".." + std::to_string(high));
    return static_cast<int>(value);
}
Options parse(int argc, char** argv) {
    Options options;
    for (int i = 1; i < argc; ++i) {
        const std::string argument = argv[i];
        auto value = [&]() -> std::string {
            if (++i >= argc) throw std::runtime_error("Missing value for " + argument);
            return argv[i];
        };
        if (argument == "--help" || argument == "-h") { options.help = true; return options; }
        else if (argument == "--version" || argument == "-v") { options.version = true; return options; }
        else if (argument == "--preset") options.preset = value();
        else if (argument == "--output") options.output = value();
        else if (argument == "--textures") options.textures.push_back(value());
        else if (argument == "--start") options.start = number(value());
        else if (argument == "--frames") options.frames = integer(value(), 2, 36000);
        else if (argument == "--width") options.width = integer(value(), 920, 8192);
        else if (argument == "--height") options.height = integer(value(), 720, 8192);
        else if (argument.starts_with('-')) throw std::runtime_error("Unknown option: " + argument);
        else if (options.bundle.empty()) options.bundle = argument;
        else throw std::runtime_error("Unexpected argument: " + argument);
    }
    if (options.bundle.empty() || options.preset.empty() || options.output.empty())
        throw std::runtime_error("Specify a bundle, --preset FILE, and --output DIRECTORY");
    if (options.start < 0) throw std::runtime_error("Start must be nonnegative");
    if (!std::filesystem::is_regular_file(options.preset)) throw std::runtime_error("Preset file does not exist");
    if (std::filesystem::exists(options.output)) throw std::runtime_error("Output directory already exists");
    for (const auto& path : options.textures)
        if (!std::filesystem::is_directory(path)) throw std::runtime_error("Texture directory does not exist: " + path);
    return options;
}
void check(bool good, const char* operation) {
    if (!good) throw std::runtime_error(std::string(operation) + ": " + SDL_GetError());
}
void preset_failed(const char*, const char* message, void* context) {
    *static_cast<std::string*>(context) = message ? message : "Unknown preset loading error";
}
struct ProjectM {
    projectm_handle handle = projectm_create();
    ~ProjectM() { if (handle) projectm_destroy(handle); }
};
std::string library_version() {
    char* value = projectm_get_version_string();
    const std::string result = value ? value : "unknown";
    projectm_free_string(value);
    return result;
}
double percentile(const std::vector<double>& sorted, double fraction) {
    const double index = fraction * (sorted.size() - 1);
    const auto left = static_cast<std::size_t>(index);
    return std::lerp(sorted[left], sorted[std::min(left + 1, sorted.size() - 1)], index - left);
}
void validate_preset(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("Cannot read preset: " + path.string());
    for (std::string line; std::getline(input, line);) {
        const auto first = line.find_first_not_of(" \t\r");
        if (first != std::string::npos &&
            line.substr(first, line.find_last_not_of(" \t\r") - first + 1) == "[preset00]") return;
    }
    throw std::runtime_error("Preset loading failed: missing [preset00] section");
}
Json::Value run(const Options& options) {
    validate_preset(options.preset);
    const auto bundle = harmonic::load_bundle(options.bundle);
    const auto audio = harmonic::decode_audio(bundle.audio_path);
    const auto audio_frames = audio.size() / harmonic::channels;
    const auto pcm_hash = harmonic::sha256(audio.data(), audio.size() * sizeof(float));
    if (audio_frames != static_cast<std::size_t>(bundle.sample_count) ||
        pcm_hash != bundle.manifest["source"]["pcm_sha256"].asString())
        throw std::runtime_error("Decoded PCM differs from the analyzer");
    const double last_time = static_cast<double>(options.frames - 1) / fps;
    if (options.start + last_time >= bundle.duration()) throw std::runtime_error("Excerpt exceeds the recording duration");
    const auto first_sample = static_cast<std::size_t>(std::llround(options.start * harmonic::sample_rate));

    SDL_SetHint(SDL_HINT_VIDEO_DRIVER, "offscreen");
    check(SDL_Init(SDL_INIT_VIDEO), "Initialize SDL offscreen video");
    struct QuitSDL { ~QuitSDL() { SDL_Quit(); } } quit;
    harmonic::Renderer renderer(options.width, options.height, true);
    int pixel_width = 0, pixel_height = 0;
    check(SDL_GetWindowSizeInPixels(renderer.window(), &pixel_width, &pixel_height), "Read output dimensions");
    if (pixel_width != options.width || pixel_height != options.height)
        throw std::runtime_error("Offscreen framebuffer dimensions differ from the requested size");
    SDL_GL_SetSwapInterval(0);
    std::string preset_error;
    ProjectM engine;
    if (!engine.handle) throw std::runtime_error("Could not create libprojectM with this OpenGL context");
    projectm_set_window_size(engine.handle, options.width, options.height);
    projectm_set_mesh_size(engine.handle, 64, 48);
    projectm_set_fps(engine.handle, fps);
    projectm_set_preset_locked(engine.handle, true);
    projectm_set_preset_switch_failed_event_callback(engine.handle, preset_failed, &preset_error);
    std::vector<const char*> texture_paths;
    for (const auto& path : options.textures) texture_paths.push_back(path.c_str());
    if (!texture_paths.empty()) projectm_set_texture_search_paths(engine.handle, texture_paths.data(), texture_paths.size());
#ifdef HARMONIC_PROJECTM_FRAME_TIME
    projectm_set_frame_time(engine.handle, 0);
#endif
    const std::string preset_path = std::filesystem::absolute(options.preset).string();
    const auto preset_hash = harmonic::sha256_file(options.preset);
    projectm_load_preset_file(engine.handle, preset_path.c_str(), false);
    if (!preset_error.empty()) throw std::runtime_error("Preset loading failed: " + preset_error);
    const auto max_samples = projectm_pcm_get_max_samples();
    if (max_samples == 0) throw std::runtime_error("libprojectM returned zero PCM buffer capacity");

    Json::Value report;
    report["harmonic_version"] = HARMONIC_VERSION;
    report["projectm_version"] = library_version();
    char* revision = projectm_get_vcs_version_string();
    report["projectm_revision"] = revision ? revision : "unknown";
    projectm_free_string(revision);
    report["gl_vendor"] = reinterpret_cast<const char*>(glGetString(GL_VENDOR));
    report["gl_renderer"] = reinterpret_cast<const char*>(glGetString(GL_RENDERER));
    report["gl_version"] = reinterpret_cast<const char*>(glGetString(GL_VERSION));
    report["preset"]["path"] = preset_path;
    report["preset"]["sha256"] = preset_hash;
    report["preset"]["texture_paths"] = Json::Value(Json::arrayValue);
    for (const auto& path : options.textures) report["preset"]["texture_paths"].append(std::filesystem::absolute(path).string());
    report["source"]["sha256"] = bundle.manifest["source"]["sha256"];
    report["source"]["pcm_sha256"] = pcm_hash;
    report["source"]["start_seconds"] = static_cast<double>(first_sample) / harmonic::sample_rate;
    report["width"] = options.width;
    report["height"] = options.height;
    report["frames"] = options.frames;
    report["timeline_fps"] = fps;
    report["pcm_max_chunk_frames"] = max_samples;
    // Some libprojectM versions recover internally from HLSL errors without
    // invoking the preset-load callback. A successful frame is not proof that
    // every original shader was used.
    report["shader_fallback_detection"] = false;
    const int warmup = std::min(30, options.frames / 4);
    report["warmup_frames"] = warmup;
#ifdef HARMONIC_PROJECTM_FRAME_TIME
    report["timing_mode"] = "explicit frame time";
#else
    report["timing_mode"] = "wall clock with 60 Hz pacing";
#endif
    std::vector<double> timings;
    std::size_t cursor = first_sample;
    harmonic::Progress progress("Rendering projectM preset", options.frames);
    const auto started = SDL_GetTicksNS();
    for (int frame = 0; frame < options.frames; ++frame) {
        const auto begin = SDL_GetTicksNS();
#ifdef HARMONIC_PROJECTM_FRAME_TIME
        const double seconds = static_cast<double>(frame) / fps;
        projectm_set_frame_time(engine.handle, seconds);
#else
        const double seconds = static_cast<double>(begin - started) / 1e9;
#endif
        const auto target = std::min(audio_frames, first_sample + static_cast<std::size_t>(seconds * harmonic::sample_rate));
        while (cursor < target) {
            const auto count = static_cast<unsigned>(std::min<std::size_t>(max_samples, target - cursor));
            projectm_pcm_add_float(engine.handle, audio.data() + cursor * harmonic::channels, count, PROJECTM_STEREO);
            cursor += count;
        }
        glBindFramebuffer(GL_FRAMEBUFFER, 0);
        glViewport(0, 0, options.width, options.height);
        projectm_opengl_render_frame(engine.handle);
        glFinish();
        if (!preset_error.empty()) throw std::runtime_error("Preset rendering failed: " + preset_error);
        const auto error = glGetError();
        if (error != GL_NO_ERROR) throw std::runtime_error("OpenGL error after rendering: " + std::to_string(error));
        if (frame >= warmup) timings.push_back(static_cast<double>(SDL_GetTicksNS() - begin) / 1e6);
#ifndef HARMONIC_PROJECTM_FRAME_TIME
        const auto next = started + static_cast<Uint64>((frame + 1) * 1e9 / fps);
        const auto now = SDL_GetTicksNS();
        if (now < next) SDL_DelayNS(next - now);
#endif
        progress.update(frame + 1);
    }
    progress.finish();
    report["wall_seconds"] = static_cast<double>(SDL_GetTicksNS() - started) / 1e9;
    report["pcm_frames_fed"] = Json::UInt64(cursor - first_sample);
    report["source"]["end_seconds"] = static_cast<double>(cursor) / harmonic::sample_rate;
    std::sort(timings.begin(), timings.end());
    report["render_ms"]["samples"] = Json::UInt64(timings.size());
    report["render_ms"]["mean"] = std::accumulate(timings.begin(), timings.end(), 0.0) / timings.size();
    report["render_ms"]["p50"] = percentile(timings, 0.5);
    report["render_ms"]["p95"] = percentile(timings, 0.95);
    report["render_ms"]["p99"] = percentile(timings, 0.99);
    report["render_ms"]["max"] = timings.back();
    report["render_ms"]["over_60hz_budget"] = Json::UInt64(std::count_if(timings.begin(), timings.end(),
        [](double value) { return value > 1000.0 / fps; }));

    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    glReadBuffer(GL_BACK);
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    std::vector<unsigned char> pixels(static_cast<std::size_t>(options.width) * options.height * 3);
    glReadPixels(0, 0, options.width, options.height, GL_RGB, GL_UNSIGNED_BYTE, pixels.data());
    if (glGetError() != GL_NO_ERROR) throw std::runtime_error("Could not read the rendered frame");
    const auto [low, high] = std::minmax_element(pixels.begin(), pixels.end());
    report["preview"]["min_component"] = *low;
    report["preview"]["max_component"] = *high;
    if (*high <= 2 || *high == *low) throw std::runtime_error("Preset produced an empty or uniform final frame");
    if (!std::filesystem::create_directories(options.output)) throw std::runtime_error("Output directory already exists");
    renderer.screenshot(options.output / "preview.ppm");
    report["preview"]["file"] = "preview.ppm";
    report["preview"]["sha256"] = harmonic::sha256_file(options.output / "preview.ppm");
    return report;
}
} // namespace

int main(int argc, char** argv) {
    if (argc == 1) { usage(); return 1; }
    try {
        const auto options = parse(argc, argv);
        if (options.help) { usage(); return 0; }
        if (options.version) { std::cout << "Harmonic " << HARMONIC_VERSION << '\n'; return 0; }
        const auto report = run(options);
        std::ofstream output(options.output / "report.json");
        output << report << '\n';
        output.close();
        if (!output) throw std::runtime_error("Could not write report.json");
        std::cout << "🟢 projectM check passed: " << report["frames"].asInt() << " frames, "
            << report["width"].asInt() << 'x' << report["height"].asInt() << ", "
            << report["gl_renderer"].asString() << ".\nReport: " << options.output / "report.json" << '\n';
    } catch (const std::exception& error) {
        std::cerr << "🔴 harmonic-projectm-check: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
