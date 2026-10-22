#include "harmonic.hpp"
#include "terminal.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <stdexcept>

namespace harmonic {
void compositor_check(Renderer& renderer, PresetRenderer& preset, const Bundle& bundle,
                      double start, const std::filesystem::path& output) {
    if (std::filesystem::exists(output)) throw std::runtime_error("Compositor output already exists");
    if (bundle.duration() < 0.5) throw std::runtime_error("Compositor check needs at least 0.5 seconds of audio");
    const double initial = std::clamp(start, 0.0, std::max(0.0, bundle.duration() - 0.3));
    auto draw = [&](double seconds, Renderer::View view) {
        int width = 0, height = 0;
        SDL_GetWindowSizeInPixels(renderer.window(), &width, &height);
        if (view != Renderer::View::graphs) preset.draw(seconds, width, height);
        renderer.draw(bundle, seconds, true, 0, true, view);
        return renderer.frame_checksum();
    };
    Progress progress("Checking playback compositor", 6);
    Json::Value report;
    report["harmonic_version"] = HARMONIC_VERSION;
    report["source_sha256"] = bundle.manifest["source"]["sha256"];
    report["source_pcm_sha256"] = bundle.manifest["source"]["pcm_sha256"];
    // A standalone graph image must remain identical after projectM changes GL state.
    const auto graph_before = draw(initial, Renderer::View::graphs);
    draw(initial, Renderer::View::combined);
    if (draw(initial, Renderer::View::graphs) != graph_before)
        throw std::runtime_error("projectM changed graph rendering state");
    report["graph_state_restored"] = true;
    report["graph_frame_sha256"] = graph_before;
    progress.update(1);
    const auto composite = draw(initial, Renderer::View::combined);
    if (composite == graph_before) throw std::runtime_error("Preset background did not reach the compositor");
    const auto rendered = preset.diagnostics()["rendered_frames"].asUInt64();
    if (draw(initial, Renderer::View::combined) != composite ||
        preset.diagnostics()["rendered_frames"].asUInt64() != rendered)
        throw std::runtime_error("Paused preset feedback or UI composition changed");
    report["paused_frame_stable"] = true;
    report["paused_frame_sha256"] = composite;
    progress.update(2);
    const double advanced = initial + 0.1;
    draw(advanced, Renderer::View::combined);
    if (preset.diagnostics()["rendered_frames"].asUInt64() <= rendered)
        throw std::runtime_error("Preset did not advance with the sample clock");
    report["sample_clock_advanced"] = true;
    progress.update(3);
    auto seek_check = [&](double seconds) {
        const auto generation = preset.diagnostics()["generation"].asUInt64();
        preset.reset();
        draw(seconds, Renderer::View::combined);
        const auto state = preset.diagnostics();
        const auto sample = static_cast<Json::UInt64>(std::llround(seconds * sample_rate));
        if (state["generation"].asUInt64() != generation + 1 || state["frames_since_reset"].asUInt64() != 1 ||
            state["sample_index"].asUInt64() != sample || state["epoch_sample_index"].asUInt64() != sample)
            throw std::runtime_error("Seek did not reset feedback to the requested sample");
    };
    seek_check(std::min(bundle.duration(), advanced + 0.1));
    seek_check(std::max(0.0, initial - 0.1));
    report["forward_and_backward_seek_reset"] = true;
    progress.update(4);
    seek_check(bundle.duration());
    const auto end = draw(bundle.duration(), Renderer::View::combined);
    if (draw(bundle.duration(), Renderer::View::combined) != end)
        throw std::runtime_error("End-of-recording preset did not remain stable");
    report["end_frame_stable"] = true;
    progress.update(5);
    if (!SDL_SetWindowSize(renderer.window(), 960, 720)) throw std::runtime_error(SDL_GetError());
    SDL_PumpEvents();
    draw(bundle.duration(), Renderer::View::combined);
    if (preset.diagnostics()["width"].asInt() != 960 || preset.diagnostics()["height"].asInt() != 720)
        throw std::runtime_error("Preset framebuffer did not resize");
    report["resize_passed"] = true;
    report["resize_state"] = preset.diagnostics();
    // Save a resumed frame rather than the artificial EOF seek used above.
    preset.reset();
    draw(initial, Renderer::View::combined);
    if (!std::filesystem::create_directories(output)) throw std::runtime_error("Compositor output already exists");
    renderer.screenshot(output / "combined.ppm");
    draw(initial, Renderer::View::preset);
    renderer.screenshot(output / "preset.ppm");
    draw(initial, Renderer::View::graphs);
    renderer.screenshot(output / "graphs.ppm");
    report["preview_seconds"] = initial;
    report["preset"] = preset.diagnostics();
    for (const auto* name : {"combined.ppm", "preset.ppm", "graphs.ppm"})
        report["previews"][name] = sha256_file(output / name);
    std::ofstream result(output / "report.json");
    result << report << '\n';
    result.close();
    if (!result) throw std::runtime_error("Could not write compositor report");
    progress.update(6);
    progress.finish();
    std::cout << "🟢 Compositor check passed: GL state, pause, sample clock, seeks, EOF, resize.\n";
}
} // namespace harmonic
