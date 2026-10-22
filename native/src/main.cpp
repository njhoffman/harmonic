#include "harmonic.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <stdexcept>

namespace {
struct Options {
    std::filesystem::path manifest, audio, render_check;
    bool inspect = false, audio_check = false;
    double start = 0, offset_ms = 0, exit_after = 0;
};
void usage() {
    std::cout << "Usage: harmonic-player BUNDLE_OR_MANIFEST [options]\n"
        "  --version             Print the built player version\n"
        "  --audio PATH          Relocate the original audio (checksum must match)\n"
        "  --start SECONDS       Start at a position in the recording\n"
        "  --offset-ms NUMBER    Feature timing offset; positive reads ahead\n"
        "  --inspect             Validate bundle, checksums, and native decoding; no devices\n"
        "  --audio-check         Check the playback clock, pause/resume, and seek; no window\n"
        "  --render-check FILE   Render one frame to PPM using SDL's offscreen driver\n"
        "  --exit-after SECONDS  Exit an interactive session after this duration\n"
        "\nControls: Space play/pause; arrows seek 5s (Shift: 30s); Home restart;\n"
        "N absolute/normalized scale; comma/period offset -/+10ms; Backspace reset offset;\n"
        "click the track envelope to seek; Escape quit.\n";
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
        if (argument == "--audio") options.audio = value();
        else if (argument == "--start") options.start = numeric(value());
        else if (argument == "--offset-ms") options.offset_ms = numeric(value());
        else if (argument == "--exit-after") options.exit_after = numeric(value());
        else if (argument == "--inspect") options.inspect = true;
        else if (argument == "--audio-check") options.audio_check = true;
        else if (argument == "--render-check") options.render_check = value();
        else if (argument.starts_with('-')) throw std::runtime_error("Unknown option: " + argument);
        else if (options.manifest.empty()) options.manifest = argument;
        else throw std::runtime_error("Unexpected argument: " + argument);
    }
    if (options.manifest.empty()) throw std::runtime_error("Specify an analysis bundle or manifest");
    if (static_cast<int>(options.inspect) + options.audio_check + !options.render_check.empty() > 1)
        throw std::runtime_error("Choose only one check mode");
    if (options.start < 0 || options.exit_after < 0) throw std::runtime_error("Start and exit-after must be nonnegative");
    return options;
}
void check(bool result, const char* operation) {
    if (!result) throw std::runtime_error(std::string(operation) + ": " + SDL_GetError());
}
void audio_check(harmonic::Transport& transport) {
    if (transport.duration() < 1) throw std::runtime_error("Audio clock check needs at least one second of audio");
    transport.resume();
    SDL_Delay(250);
    const double playing = transport.position();
    if (playing <= 0 || playing > 0.5) throw std::runtime_error("Playback clock did not advance normally");
    transport.pause();
    const double paused = transport.position();
    SDL_Delay(120);
    if (transport.position() != paused) throw std::runtime_error("Paused playback clock moved");
    const double target = std::min(transport.duration() / 2, 12.345);
    transport.seek(target);
    if (std::abs(transport.position() - target) > 1.0 / harmonic::sample_rate)
        throw std::runtime_error("Seek did not land on the requested sample");
    transport.resume();
    SDL_Delay(180);
    if (transport.position() <= target) throw std::runtime_error("Playback did not resume after seeking");
    transport.seek(0);
    SDL_Delay(120);
    if (transport.position() > 0.4) throw std::runtime_error("Playing seek did not reset the clock");
    transport.seek(transport.duration() - 0.08);
    SDL_Delay(250);
    if (std::abs(transport.position() - transport.duration()) > 1.0 / harmonic::sample_rate)
        throw std::runtime_error("Playback clock did not reach the final sample");
    transport.pause();
    if (!transport.error().empty()) throw std::runtime_error("Audio callback: " + transport.error());
    std::cout << "Audio clock check passed: advance, freeze, seek, resume, playing seek, end of file.\n"
              << "Estimated device chunk: " << transport.buffer_seconds() * 1000 << " ms.\n";
}
} // namespace

int main(int argc, char** argv) {
    if (argc == 2 && std::string(argv[1]) == "--version") {
        std::cout << "Harmonic " << HARMONIC_VERSION << '\n';
        return 0;
    }
    if (argc == 1 || (argc == 2 && std::string(argv[1]) == "--help")) {
        usage();
        return argc == 1 ? 1 : 0;
    }
    try {
        const auto options = parse(argc, argv);
        const auto bundle = harmonic::load_bundle(options.manifest, options.audio);
        std::cout << "Decoding " << bundle.audio_path.filename().string() << "...\n";
        const auto audio = harmonic::decode_audio(bundle.audio_path);
        if (static_cast<std::int64_t>(audio.size() / harmonic::channels) != bundle.sample_count)
            throw std::runtime_error("Decoded sample count differs from the analysis; regenerate the bundle with the current FFmpeg");
        if (harmonic::sha256(audio.data(), audio.size() * sizeof(float)) != bundle.manifest["source"]["pcm_sha256"].asString())
            throw std::runtime_error("Decoded PCM differs from the analyzer; regenerate with this FFmpeg version");
        std::cout << "Validated " << bundle.duration() << "s, " << bundle.rms.size() << " feature frames, "
                  << bundle.bands << " bands; source, artifact, and decoded PCM checksums match.\n";
        if (options.inspect) return 0;
        const bool render_check = !options.render_check.empty();
        if (render_check) SDL_SetHint(SDL_HINT_VIDEO_DRIVER, "offscreen");
        check(SDL_Init(render_check ? SDL_INIT_VIDEO : (options.audio_check ? SDL_INIT_AUDIO : SDL_INIT_AUDIO | SDL_INIT_VIDEO)), "Initialize SDL");
        struct QuitSDL { ~QuitSDL() { SDL_Quit(); } } quit;
        if (render_check) {
            harmonic::Renderer renderer(1280, 720, true);
            renderer.draw(bundle, std::min(options.start, bundle.duration()), true, options.offset_ms / 1000, true);
            renderer.screenshot(options.render_check);
            std::cout << "Rendered " << options.render_check << '\n';
            return 0;
        }
        harmonic::Transport transport(audio);
        if (options.audio_check) { audio_check(transport); return 0; }
        harmonic::Renderer renderer(1280, 720, false);
        transport.seek(options.start);
        transport.resume();
        bool running = true, relative = true;
        double offset = options.offset_ms / 1000;
        const Uint64 started = SDL_GetTicksNS();
        auto toggle = [&] {
            if (transport.paused()) {
                if (transport.position() >= transport.duration()) transport.seek(0);
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
                    case SDLK_LEFT: transport.seek(transport.position() - step); break;
                    case SDLK_RIGHT: transport.seek(transport.position() + step); break;
                    case SDLK_HOME: transport.seek(0); break;
                    case SDLK_N: relative = !relative; break;
                    case SDLK_COMMA: offset = std::max(-2.0, offset - 0.01); break;
                    case SDLK_PERIOD: offset = std::min(2.0, offset + 0.01); break;
                    case SDLK_BACKSPACE: offset = 0; break;
                    default: break;
                    }
                }
                if (event.type == SDL_EVENT_MOUSE_BUTTON_DOWN && event.button.button == SDL_BUTTON_LEFT) {
                    int width, height;
                    SDL_GetWindowSize(renderer.window(), &width, &height);
                    const float x = event.button.x - harmonic::Renderer::timeline_left, y = event.button.y;
                    if (x >= 0 && x <= width - 2 * harmonic::Renderer::timeline_left && y >= 470 && y <= 605)
                        transport.seek(x / (width - 2 * harmonic::Renderer::timeline_left) * bundle.duration());
                    else if (y >= 625 && y <= 663) {
                        if (x >= 0 && x <= 118) toggle();
                        else if (x >= 132 && x <= 258) transport.seek(0);
                        else if (x >= 272 && x <= 466) relative = !relative;
                    }
                }
                if (event.type == SDL_EVENT_AUDIO_DEVICE_REMOVED && !event.adevice.recording && !transport.paused())
                    transport.pause();
            }
            const double position = transport.position();
            if (position >= transport.duration() && !transport.paused()) transport.pause();
            if (!transport.error().empty()) throw std::runtime_error("Audio callback: " + transport.error());
            renderer.draw(bundle, position, transport.paused(), offset, relative);
            SDL_GL_SwapWindow(renderer.window());
            SDL_Delay(1);
            if (options.exit_after > 0 && static_cast<double>(SDL_GetTicksNS() - started) / 1e9 >= options.exit_after) running = false;
        }
    } catch (const std::exception& error) {
        std::cerr << "harmonic-player: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
