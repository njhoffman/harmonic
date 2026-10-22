#include "harmonic.hpp"
#include "terminal.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <stdexcept>

namespace {
struct Options {
    std::filesystem::path manifest, audio, render_check, preset, compositor_check;
    std::vector<std::string> textures;
    bool help = false, version = false, inspect = false, audio_check = false;
    bool explicit_view = false;
    harmonic::Renderer::View view = harmonic::Renderer::View::graphs;
    int render_frames = 1;
    double start = 0, offset_ms = 0, exit_after = 0;
};
void usage() {
    std::cout << "Usage: harmonic-player BUNDLE_OR_MANIFEST [options]\n"
        "  -h, --help            Show usage and controls\n"
        "  -v, --version         Print the built player version\n"
        "  --audio PATH          Relocate the original audio (checksum must match)\n"
        "  --preset FILE         Play a local projectM preset behind the graph UI\n"
        "  --textures PATH       Preset texture directory (repeatable)\n"
        "  --view MODE           combined, preset, or graphs (default: combined with preset)\n"
        "  --start SECONDS       Start at a position in the recording\n"
        "  --offset-ms NUMBER    Feature timing offset; positive reads ahead\n"
        "  --inspect             Validate bundle, checksums, and native decoding; no devices\n"
        "  --audio-check         Check the playback clock, pause/resume, and seek; no window\n"
        "  --render-check FILE   Render one frame to PPM using SDL's offscreen driver\n"
        "  --render-frames N     Render N frames at 60 Hz from --start in render-check mode\n"
        "  --compositor-check DIR  Check preset pause/seek/resize offscreen; save views/report\n"
        "  --exit-after SECONDS  Exit an interactive session after this duration\n"
        "\nControls: Space play/pause; arrows seek 5s (Shift: 30s); Home restart;\n"
        "N absolute/normalized scale; V preset/graphs view; comma/period offset -/+10ms;\n"
        "Backspace reset offset; click the track envelope to seek; Escape quit.\n"
        "\nprojectM playback: " << (harmonic::projectm_playback_available() ? "enabled" : "disabled") << '\n';
}
double numeric(const std::string& value) {
    std::size_t end = 0;
    const double result = std::stod(value, &end);
    if (end != value.size() || !std::isfinite(result)) throw std::runtime_error("Invalid number: " + value);
    return result;
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
        else if (argument == "--audio") options.audio = value();
        else if (argument == "--preset") options.preset = value();
        else if (argument == "--textures") options.textures.push_back(value());
        else if (argument == "--view") {
            const auto mode = value();
            if (mode == "combined") options.view = harmonic::Renderer::View::combined;
            else if (mode == "preset") options.view = harmonic::Renderer::View::preset;
            else if (mode == "graphs") options.view = harmonic::Renderer::View::graphs;
            else throw std::runtime_error("View must be combined, preset, or graphs");
            options.explicit_view = true;
        }
        else if (argument == "--start") options.start = numeric(value());
        else if (argument == "--offset-ms") options.offset_ms = numeric(value());
        else if (argument == "--exit-after") options.exit_after = numeric(value());
        else if (argument == "--inspect") options.inspect = true;
        else if (argument == "--audio-check") options.audio_check = true;
        else if (argument == "--render-check") options.render_check = value();
        else if (argument == "--compositor-check") options.compositor_check = value();
        else if (argument == "--render-frames") {
            const double count = numeric(value());
            if (count < 1 || count > 36000 || count != std::floor(count))
                throw std::runtime_error("Render frames must be an integer in 1..36000");
            options.render_frames = static_cast<int>(count);
        }
        else if (argument.starts_with('-')) throw std::runtime_error("Unknown option: " + argument);
        else if (options.manifest.empty()) options.manifest = argument;
        else throw std::runtime_error("Unexpected argument: " + argument);
    }
    if (options.manifest.empty()) throw std::runtime_error("Specify an analysis bundle or manifest");
    if (static_cast<int>(options.inspect) + options.audio_check + !options.render_check.empty() + !options.compositor_check.empty() > 1)
        throw std::runtime_error("Choose only one check mode");
    if (options.start < 0 || options.exit_after < 0) throw std::runtime_error("Start and exit-after must be nonnegative");
    if (options.preset.empty() && (!options.textures.empty() || !options.compositor_check.empty() ||
                                  options.view != harmonic::Renderer::View::graphs))
        throw std::runtime_error("Preset view, texture paths, and compositor-check require --preset FILE");
    if (!options.preset.empty()) {
        if (options.inspect || options.audio_check) throw std::runtime_error("Preset options require playback or a video check mode");
        if (!harmonic::projectm_playback_available())
            throw std::runtime_error("projectM playback is unavailable in this build; see README optional projectM setup");
        if (!options.explicit_view) options.view = harmonic::Renderer::View::combined;
    }
    if (options.render_frames != 1 && options.render_check.empty()) throw std::runtime_error("--render-frames requires --render-check");
    return options;
}
void check(bool result, const char* operation) {
    if (!result) throw std::runtime_error(std::string(operation) + ": " + SDL_GetError());
}
void audio_check(harmonic::Transport& transport) {
    if (transport.duration() < 1) throw std::runtime_error("Audio clock check needs at least one second of audio");
    auto wait_for_progress = [&](const char* operation, double floor, Uint64 started, bool until_end = false) {
        const double target = until_end ? transport.duration() : std::min(transport.duration(), floor + 0.02);
        double previous = floor;
        while (true) {
            const double position = transport.position();
            const double elapsed = static_cast<double>(SDL_GetTicksNS() - started) / 1e9;
            if (position + 1.0 / harmonic::sample_rate < previous ||
                position - floor > elapsed + transport.buffer_seconds() + 0.075)
                throw std::runtime_error(std::string(operation) + ": clock jumped (position " +
                    std::to_string(position) + ", elapsed " + std::to_string(elapsed) + ")");
            if (!transport.error().empty()) throw std::runtime_error("Audio callback: " + transport.error());
            if (position >= target - 1.0 / harmonic::sample_rate) return;
            if (elapsed > 2.0) throw std::runtime_error(std::string(operation) + ": clock did not reach " +
                std::to_string(target) + " within 2 seconds (position " + std::to_string(position) + ")");
            previous = position;
            SDL_Delay(10);
        }
    };
    auto started = SDL_GetTicksNS();
    transport.resume();
    wait_for_progress("Initial playback", 0, started);
    transport.pause();
    const double paused = transport.position();
    SDL_Delay(120);
    if (transport.position() != paused) throw std::runtime_error("Paused playback clock moved");
    const double target = std::min(transport.duration() / 2, 12.345);
    transport.seek(target);
    if (std::abs(transport.position() - target) > 1.0 / harmonic::sample_rate)
        throw std::runtime_error("Seek did not land on the requested sample");
    started = SDL_GetTicksNS();
    transport.resume();
    wait_for_progress("Resume after seek", target, started);
    started = SDL_GetTicksNS();
    transport.seek(0);
    wait_for_progress("Playing seek", 0, started);
    started = SDL_GetTicksNS();
    transport.seek(transport.duration() - 0.08);
    wait_for_progress("End of recording", transport.duration() - 0.08, started, true);
    transport.pause();
    if (!transport.error().empty()) throw std::runtime_error("Audio callback: " + transport.error());
    std::cout << "🟢 Audio clock check passed: advance, freeze, seek, resume, playing seek, end of file.\n"
              << "Estimated device chunk: " << transport.buffer_seconds() * 1000 << " ms.\n";
}
} // namespace

int main(int argc, char** argv) {
    if (argc == 1) {
        usage();
        return 1;
    }
    try {
        const auto options = parse(argc, argv);
        if (options.help) { usage(); return 0; }
        if (options.version) {
            std::cout << "Harmonic " << HARMONIC_VERSION << '\n';
            return 0;
        }
        const auto bundle = harmonic::load_bundle(options.manifest, options.audio);
        std::cout << "🔵 Decoding " << bundle.audio_path.filename().string() << "...\n";
        const auto audio = harmonic::decode_audio(bundle.audio_path);
        if (static_cast<std::int64_t>(audio.size() / harmonic::channels) != bundle.sample_count)
            throw std::runtime_error("Decoded sample count differs from the analysis; regenerate the bundle with the current FFmpeg");
        if (harmonic::sha256(audio.data(), audio.size() * sizeof(float)) != bundle.manifest["source"]["pcm_sha256"].asString())
            throw std::runtime_error("Decoded PCM differs from the analyzer; regenerate with this FFmpeg version");
        std::cout << "🟢 Validated " << bundle.duration() << "s, " << bundle.rms.size() << " feature frames, "
                  << bundle.bands << " bands; source, artifact, and decoded PCM checksums match.\n";
        if (options.inspect) return 0;
        const bool video_check = !options.render_check.empty() || !options.compositor_check.empty();
        if (video_check) SDL_SetHint(SDL_HINT_VIDEO_DRIVER, "offscreen");
        check(SDL_Init(video_check ? SDL_INIT_VIDEO : (options.audio_check ? SDL_INIT_AUDIO : SDL_INIT_AUDIO | SDL_INIT_VIDEO)), "Initialize SDL");
        struct QuitSDL { ~QuitSDL() { SDL_Quit(); } } quit;
        if (video_check) {
            harmonic::Renderer renderer(1280, 720, true);
            std::unique_ptr<harmonic::PresetRenderer> preset;
            if (!options.preset.empty()) preset = std::make_unique<harmonic::PresetRenderer>(audio, options.preset, options.textures);
            if (!options.compositor_check.empty()) {
                harmonic::compositor_check(renderer, *preset, bundle, options.start, options.compositor_check);
                return 0;
            }
            harmonic::Progress progress("Rendering playback preview", options.render_frames);
            for (int frame = 0; frame < options.render_frames; ++frame) {
                const double seconds = std::min(options.start + frame / 60.0, bundle.duration());
                if (preset && options.view != harmonic::Renderer::View::graphs) {
                    int width = 0, height = 0;
                    SDL_GetWindowSizeInPixels(renderer.window(), &width, &height);
                    preset->draw(std::clamp(seconds + options.offset_ms / 1000, 0.0, bundle.duration()), width, height);
                }
                renderer.draw(bundle, seconds, true, options.offset_ms / 1000, true, options.view);
                progress.update(frame + 1);
            }
            renderer.screenshot(options.render_check);
            progress.finish();
            std::cout << "🟢 Rendered " << options.render_check << '\n';
            return 0;
        }
        harmonic::Transport transport(audio);
        if (options.audio_check) { audio_check(transport); return 0; }
        harmonic::Renderer renderer(1280, 720, false);
        std::unique_ptr<harmonic::PresetRenderer> preset;
        if (!options.preset.empty()) {
            preset = std::make_unique<harmonic::PresetRenderer>(audio, options.preset, options.textures);
            const auto title = "Harmonic / " + options.preset.stem().string();
            SDL_SetWindowTitle(renderer.window(), title.c_str());
        }
        bool running = true, relative = true;
        double offset = options.offset_ms / 1000;
        auto view = options.view;
        auto prepare_preset = [&](double position) {
            if (preset && view != harmonic::Renderer::View::graphs) {
                int width = 0, height = 0;
                SDL_GetWindowSizeInPixels(renderer.window(), &width, &height);
                if (width > 0 && height > 0) preset->draw(std::clamp(position + offset, 0.0, bundle.duration()), width, height);
            }
        };
        auto reset_preset = [&] {
            if (!preset) return;
            const bool playing = !transport.paused();
            if (playing) transport.pause();
            preset->reset();
            prepare_preset(transport.position());
            if (playing) transport.resume();
        };
        auto seek = [&](double seconds) {
            if (!preset) { transport.seek(seconds); return; }
            // Compile/reset feedback while the audio clock is held, so startup
            // and seeks do not play past a still-compiling first preset frame.
            const bool playing = !transport.paused();
            if (playing) transport.pause();
            transport.seek(seconds);
            reset_preset();
            if (playing) transport.resume();
        };
        auto set_offset = [&](double seconds) { offset = seconds; reset_preset(); };
        seek(options.start);
        transport.resume();
        const Uint64 started = SDL_GetTicksNS();
        auto toggle = [&] {
            if (transport.paused()) {
                if (transport.position() >= transport.duration()) seek(0);
                transport.resume();
            } else transport.pause();
        };
        while (running) {
            SDL_Event event;
            while (SDL_PollEvent(&event)) {
                if (event.type == SDL_EVENT_QUIT) running = false;
                if (event.type == SDL_EVENT_KEY_DOWN && !event.key.repeat) {
                    const double step = event.key.mod & SDL_KMOD_SHIFT ? 30 : 5;
                    switch (event.key.key) {
                    case SDLK_ESCAPE: running = false; break;
                    case SDLK_SPACE: toggle(); break;
                    case SDLK_LEFT: seek(transport.position() - step); break;
                    case SDLK_RIGHT: seek(transport.position() + step); break;
                    case SDLK_HOME: seek(0); break;
                    case SDLK_N: relative = !relative; break;
                    case SDLK_V:
                        if (preset) {
                            if (view == harmonic::Renderer::View::combined) view = harmonic::Renderer::View::preset;
                            else if (view == harmonic::Renderer::View::preset) view = harmonic::Renderer::View::graphs;
                            else { view = harmonic::Renderer::View::combined; reset_preset(); }
                        }
                        break;
                    case SDLK_COMMA: set_offset(std::max(-2.0, offset - 0.01)); break;
                    case SDLK_PERIOD: set_offset(std::min(2.0, offset + 0.01)); break;
                    case SDLK_BACKSPACE: set_offset(0); break;
                    default: break;
                    }
                }
                if (event.type == SDL_EVENT_MOUSE_BUTTON_DOWN && event.button.button == SDL_BUTTON_LEFT) {
                    int width, height;
                    SDL_GetWindowSize(renderer.window(), &width, &height);
                    const float x = event.button.x - harmonic::Renderer::timeline_left, y = event.button.y;
                    if (x >= 0 && x <= width - 2 * harmonic::Renderer::timeline_left && y >= 470 && y <= 605)
                        seek(x / (width - 2 * harmonic::Renderer::timeline_left) * bundle.duration());
                    else if (y >= 625 && y <= 663) {
                        if (x >= 0 && x <= 118) toggle();
                        else if (x >= 132 && x <= 258) seek(0);
                        else if (x >= 272 && x <= 466) relative = !relative;
                    }
                }
                if (event.type == SDL_EVENT_AUDIO_DEVICE_REMOVED && !event.adevice.recording && !transport.paused())
                    transport.pause();
            }
            const double position = transport.position();
            if (position >= transport.duration() && !transport.paused()) transport.pause();
            if (!transport.error().empty()) throw std::runtime_error("Audio callback: " + transport.error());
            prepare_preset(position);
            renderer.draw(bundle, position, transport.paused(), offset, relative, view);
            SDL_GL_SwapWindow(renderer.window());
            SDL_Delay(1);
            if (options.exit_after > 0 && static_cast<double>(SDL_GetTicksNS() - started) / 1e9 >= options.exit_after) running = false;
        }
    } catch (const std::exception& error) {
        std::cerr << "🔴 harmonic-player: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
