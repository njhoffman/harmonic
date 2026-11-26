#include "harmonic.hpp"
#include "terminal.hpp"

#include <SDL3/SDL_opengl.h>

#include <algorithm>
#include <cmath>
#include <iostream>
#include <stdexcept>

namespace {
struct Options {
    std::filesystem::path manifest, audio, render_check, preset, compositor_check, frame_report;
    std::vector<std::string> textures;
    bool help = false, version = false, inspect = false, audio_check = false;
    bool explicit_view = false, residuals = false, fullscreen = false, explicit_offset = false, save_offset = false;
    int width = 1280, height = 720;
    harmonic::Renderer::View view = harmonic::Renderer::View::graphs;
    int render_frames = 1;
    double start = 0, offset_ms = 0, exit_after = 0, seek_every = 0;
};
const char* view_name(harmonic::Renderer::View view) {
    switch (view) {
    case harmonic::Renderer::View::combined: return "combined";
    case harmonic::Renderer::View::preset: return "preset";
    default: return "graphs";
    }
}
std::string gl_string(GLenum name) {
    const auto* value = reinterpret_cast<const char*>(glGetString(name));
    return value ? value : "";
}
void usage() {
    std::cout << "Usage: harmonic-player BUNDLE_OR_MANIFEST [options]\n"
        "  -h, --help            Show usage and controls\n"
        "  -v, --version         Print the built player version\n"
        "  --audio PATH          Relocate the original audio (checksum must match)\n"
        "  --preset FILE         Play a local projectM preset behind the graph UI\n"
        "  --textures PATH       Preset texture directory (repeatable)\n"
        "  --view MODE           combined, preset, or graphs (default: combined with preset)\n"
        "  --sources MODE        Show SAM targets (default) or residuals in source graphs\n"
        "  --start SECONDS       Start at a position in the recording\n"
        "  --offset-ms NUMBER    Feature timing offset; positive reads ahead (overrides a saved offset)\n"
        "  --save-offset         Save --offset-ms for the current output device and exit\n"
        "  --inspect             Validate bundle, checksums, and native decoding; no devices\n"
        "  --audio-check         Check the playback clock, pause/resume, and seek; no window\n"
        "  --render-check FILE   Render one frame to PPM using SDL's offscreen driver\n"
        "  --render-frames N     Render N frames at 60 Hz from --start in render-check mode\n"
        "  --compositor-check DIR  Check preset pause/seek/resize offscreen; save views/report\n"
        "  --exit-after SECONDS  Exit an interactive session after this duration\n"
        "  --size WxH            Initial window size (default 1280x720)\n"
        "  --fullscreen          Open fullscreen at the desktop resolution\n"
        "  --frame-report FILE   Record frame, GPU, and seek timing to JSON (needs --exit-after)\n"
        "  --seek-every SECONDS  Scripted seeks during a frame report\n"
        "\nControls: Space play/pause; arrows seek 5s (Shift: 30s); Home restart;\n"
        "N absolute/normalized scale; R targets/residuals; V preset/graphs view; comma/period offset -/+10ms;\n"
        "Backspace reset offset; S save offset for this output device; click the track envelope to seek;\n"
        "Escape quit. Saved offsets live in $XDG_CONFIG_HOME/harmonic/calibration.json.\n"
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
        else if (argument == "--sources") {
            const auto mode = value();
            if (mode != "targets" && mode != "residuals") throw std::runtime_error("Sources must be targets or residuals");
            options.residuals = mode == "residuals";
        }
        else if (argument == "--start") options.start = numeric(value());
        else if (argument == "--offset-ms") {
            options.offset_ms = numeric(value());
            options.explicit_offset = true;
        }
        else if (argument == "--save-offset") options.save_offset = true;
        else if (argument == "--exit-after") options.exit_after = numeric(value());
        else if (argument == "--size") {
            const auto size = value();
            const auto split = size.find('x');
            const auto dimension = [&](const std::string& part) {
                const double number = part.empty() || part.find_first_not_of("0123456789") != std::string::npos ? -1 : numeric(part);
                if (number < 320 || number > 7680) throw std::runtime_error("Size must be WxH with each side in 320..7680");
                return static_cast<int>(number);
            };
            if (split == std::string::npos) throw std::runtime_error("Size must be WxH with each side in 320..7680");
            options.width = dimension(size.substr(0, split));
            options.height = dimension(size.substr(split + 1));
        }
        else if (argument == "--fullscreen") options.fullscreen = true;
        else if (argument == "--frame-report") options.frame_report = value();
        else if (argument == "--seek-every") options.seek_every = numeric(value());
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
    if (std::abs(options.offset_ms) > harmonic::max_offset_seconds * 1000)
        throw std::runtime_error("Offset must be within +/-2000 ms");
    const bool check_mode = options.inspect || options.audio_check || !options.render_check.empty() || !options.compositor_check.empty();
    if (options.save_offset && (!options.explicit_offset || check_mode || !options.frame_report.empty() || !options.preset.empty()))
        throw std::runtime_error("--save-offset needs --offset-ms and no check, preset, or report options");
    if (check_mode && (options.fullscreen || !options.frame_report.empty()))
        throw std::runtime_error("--fullscreen and --frame-report apply to interactive playback only");
    if (!options.frame_report.empty() && options.exit_after <= 0) throw std::runtime_error("--frame-report requires --exit-after");
    if (options.seek_every < 0) throw std::runtime_error("Seek-every must be nonnegative");
    if (options.seek_every > 0 && options.frame_report.empty()) throw std::runtime_error("--seek-every requires --frame-report");
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
        if (options.inspect) {
            if (!bundle.sources.empty()) {
                Json::Value diagnostics;
                for (const auto& source : bundle.sources) {
                    Json::Value item;
                    item["name"] = source.name;
                    item["start_sample"] = Json::Int64(source.start_sample);
                    item["sample_count"] = Json::Int64(source.sample_count);
                    item["covered"] = source.covers(options.start);
                    if (source.covers(options.start)) {
                        item["rms"] = source.interpolate(source.rms, options.start);
                        item["peak"] = source.interpolate(source.peak, options.start);
                        item["onset"] = source.interpolate(source.onset, options.start);
                    }
                    if (source.role == "target") {
                        const auto* presence = bundle.presence_for(source.target);
                        // Missing presence is unknown, not a zero probability.
                        if (presence && presence->covers(options.start)) {
                            item["presence"] = presence->at(options.start);
                            item["presence_reliability"] = presence->reliability;
                        }
                    }
                    diagnostics["source_features"].append(item);
                }
                Json::StreamWriterBuilder writer;
                writer["indentation"] = "";
                std::cout << Json::writeString(writer, diagnostics) << '\n';
            }
            return 0;
        }
        const bool video_check = !options.render_check.empty() || !options.compositor_check.empty();
        if (video_check) SDL_SetHint(SDL_HINT_VIDEO_DRIVER, "offscreen");
        check(SDL_Init(video_check ? SDL_INIT_VIDEO : (options.audio_check || options.save_offset ? SDL_INIT_AUDIO : SDL_INIT_AUDIO | SDL_INIT_VIDEO)), "Initialize SDL");
        struct QuitSDL { ~QuitSDL() { SDL_Quit(); } } quit;
        if (video_check) {
            harmonic::Renderer renderer(1280, 720, true);
            renderer.set_residuals(options.residuals);
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
        const auto device = transport.device_key();
        std::filesystem::path calibration_file;
        std::optional<double> saved_ms;
        try {
            calibration_file = harmonic::calibration_path();
            const auto calibration = harmonic::load_calibration(calibration_file, device);
            if (!calibration.error.empty())
                std::cerr << "🟡 Ignoring " << calibration_file.string() << ": " << calibration.error << '\n';
            saved_ms = calibration.offset_ms;
        } catch (const std::exception& error) {
            std::cerr << "🟡 " << error.what() << '\n';
        }
        if (options.save_offset) {
            if (calibration_file.empty()) throw std::runtime_error("No calibration file location");
            harmonic::save_calibration(calibration_file, device, options.offset_ms);
            std::cout << "🟢 Saved offset " << options.offset_ms << " ms for " << device << " in "
                      << calibration_file.string() << '\n';
            return 0;
        }
        harmonic::Renderer renderer(options.width, options.height, false);
        if (options.fullscreen) {
            check(SDL_SetWindowFullscreen(renderer.window(), true), "Enter fullscreen");
            SDL_SyncWindow(renderer.window());
        }
        bool residuals = options.residuals;
        renderer.set_residuals(residuals);
        std::unique_ptr<harmonic::PresetRenderer> preset;
        if (!options.preset.empty()) {
            preset = std::make_unique<harmonic::PresetRenderer>(audio, options.preset, options.textures);
            const auto title = "Harmonic / " + options.preset.stem().string();
            SDL_SetWindowTitle(renderer.window(), title.c_str());
        }
        bool running = true, relative = true;
        double offset = options.offset_ms / 1000;
        std::string offset_source = options.explicit_offset ? "argument" : "default";
        if (!options.explicit_offset && saved_ms) {
            offset = *saved_ms / 1000;
            offset_source = "device";
            std::cout << "🔵 Applying saved offset " << *saved_ms << " ms for " << device << '\n';
        }
        const double initial_offset_ms = offset * 1000;
        auto same_ms = [](double a, double b) { return std::abs(a - b) < 0.05; };
        auto update_offset_label = [&] {
            const double ms = offset * 1000;
            if (saved_ms && same_ms(ms, *saved_ms)) renderer.set_offset_label("DEVICE");
            else if (options.explicit_offset && same_ms(ms, options.offset_ms)) renderer.set_offset_label("ARG");
            else if (saved_ms || !same_ms(ms, 0)) renderer.set_offset_label("UNSAVED");
            else renderer.set_offset_label("");
        };
        update_offset_label();
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
        std::unique_ptr<harmonic::FrameTimer> timer;
        if (!options.frame_report.empty()) timer = std::make_unique<harmonic::FrameTimer>();
        auto seek_now = [&](double seconds) {
            if (!preset) { transport.seek(seconds); return; }
            // Compile/reset feedback while the audio clock is held, so startup
            // and seeks do not play past a still-compiling first preset frame.
            const bool playing = !transport.paused();
            if (playing) transport.pause();
            transport.seek(seconds);
            reset_preset();
            if (playing) transport.resume();
        };
        auto seek = [&](double seconds) {
            if (!timer) { seek_now(seconds); return; }
            const double from = transport.position();
            const Uint64 requested = SDL_GetTicksNS();
            seek_now(seconds);
            timer->seek(requested, SDL_GetTicksNS(), from, transport.position());
        };
        auto set_offset = [&](double seconds) { offset = seconds; reset_preset(); update_offset_label(); };
        auto save_offset = [&] {
            // A failed save is reported but never interrupts playback.
            try {
                if (calibration_file.empty()) throw std::runtime_error("No calibration file location");
                harmonic::save_calibration(calibration_file, device, offset * 1000);
                saved_ms = std::round(offset * 10000) / 10;
                update_offset_label();
                std::cout << "🟢 Saved offset " << *saved_ms << " ms for " << device << '\n';
            } catch (const std::exception& error) {
                std::cerr << "🔴 Offset not saved: " << error.what() << '\n';
            }
        };
        seek(options.start);
        transport.resume();
        const Uint64 started = SDL_GetTicksNS();
        int scripted_seeks = 0;
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
                    case SDLK_R:
                        residuals = !residuals;
                        renderer.set_residuals(residuals);
                        break;
                    case SDLK_N: relative = !relative; break;
                    case SDLK_V:
                        if (preset) {
                            if (view == harmonic::Renderer::View::combined) view = harmonic::Renderer::View::preset;
                            else if (view == harmonic::Renderer::View::preset) view = harmonic::Renderer::View::graphs;
                            else { view = harmonic::Renderer::View::combined; reset_preset(); }
                        }
                        break;
                    case SDLK_COMMA: set_offset(std::max(-harmonic::max_offset_seconds, offset - 0.01)); break;
                    case SDLK_PERIOD: set_offset(std::min(harmonic::max_offset_seconds, offset + 0.01)); break;
                    case SDLK_S: save_offset(); break;
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
            if (timer && options.seek_every > 0 &&
                static_cast<double>(SDL_GetTicksNS() - started) / 1e9 >= options.seek_every * (scripted_seeks + 1)) {
                // Deterministic targets spread over the recording, away from its end.
                ++scripted_seeks;
                seek(std::fmod(options.start + 23.0 * scripted_seeks, std::max(1.0, bundle.duration() - 1)));
            }
            const double position = transport.position();
            if (position >= transport.duration() && !transport.paused()) transport.pause();
            if (!transport.error().empty()) throw std::runtime_error("Audio callback: " + transport.error());
            if (timer) timer->begin(SDL_GetTicksNS(), position, transport.queued_frames());
            prepare_preset(position);
            renderer.draw(bundle, position, transport.paused(), offset, relative, view);
            if (timer) timer->drawn(SDL_GetTicksNS());
            SDL_GL_SwapWindow(renderer.window());
            if (timer) timer->swapped(SDL_GetTicksNS());
            SDL_Delay(1);
            if (options.exit_after > 0 && static_cast<double>(SDL_GetTicksNS() - started) / 1e9 >= options.exit_after) running = false;
        }
        if (timer) {
            Json::Value context;
            context["player_version"] = HARMONIC_VERSION;
            context["manifest"] = std::filesystem::absolute(options.manifest).string();
            context["source_sha256"] = bundle.manifest["source"]["sha256"];
            context["view"] = view_name(view);
            context["preset"] = preset ? Json::Value(std::filesystem::absolute(options.preset).string()) : Json::Value();
            context["preset_sha256"] = preset ? Json::Value(harmonic::sha256_file(options.preset)) : Json::Value();
            context["start"] = options.start;
            context["exit_after"] = options.exit_after;
            context["seek_every"] = options.seek_every;
            context["gl"]["vendor"] = gl_string(GL_VENDOR);
            context["gl"]["renderer"] = gl_string(GL_RENDERER);
            context["gl"]["version"] = gl_string(GL_VERSION);
            int swap_interval = 0;
            context["gl"]["swap_interval"] = SDL_GL_GetSwapInterval(&swap_interval) ? Json::Value(swap_interval) : Json::Value();
            auto& display = context["display"];
            display["video_driver"] = SDL_GetCurrentVideoDriver() ? SDL_GetCurrentVideoDriver() : "";
            const auto* mode = SDL_GetCurrentDisplayMode(SDL_GetDisplayForWindow(renderer.window()));
            display["refresh_hz"] = mode && mode->refresh_rate > 0 ? Json::Value(mode->refresh_rate) : Json::Value();
            display["mode_width"] = mode ? mode->w : 0;
            display["mode_height"] = mode ? mode->h : 0;
            int pixel_width = 0, pixel_height = 0;
            SDL_GetWindowSizeInPixels(renderer.window(), &pixel_width, &pixel_height);
            display["pixel_width"] = pixel_width;
            display["pixel_height"] = pixel_height;
            display["fullscreen"] = (SDL_GetWindowFlags(renderer.window()) & SDL_WINDOW_FULLSCREEN) != 0;
            auto& output = context["audio"];
            output["driver"] = SDL_GetCurrentAudioDriver() ? SDL_GetCurrentAudioDriver() : "";
            output["sample_rate"] = harmonic::sample_rate;
            output["device_buffer_seconds"] = transport.buffer_seconds();
            output["device"] = device;
            context["offset"]["initial_ms"] = initial_offset_ms;
            context["offset"]["final_ms"] = offset * 1000;
            context["offset"]["source"] = offset_source;
            timer->write(options.frame_report, context);
            std::cout << "🟢 Frame report: " << options.frame_report.string() << '\n';
        }
    } catch (const std::exception& error) {
        std::cerr << "🔴 harmonic-player: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
