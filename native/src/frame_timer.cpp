#include "harmonic.hpp"

#include <SDL3/SDL_opengl.h>

#include <cmath>
#include <fstream>
#include <limits>
#include <stdexcept>

namespace harmonic {
namespace {
// A seek settles once the audio clock has advanced this far past its target.
constexpr double settle_advance_seconds = 0.005;
} // namespace

FrameTimer::FrameTimer() {
    glGenQueries(ring * 2, queries_);
    origin_ = SDL_GetTicksNS();
}

FrameTimer::~FrameTimer() { glDeleteQueries(ring * 2, queries_); }

void FrameTimer::collect(bool wait) {
    for (int slot = 0; slot < ring; ++slot) {
        auto& pending = pending_[slot];
        if (!pending.active) continue;
        GLint available = 0;
        if (!wait) {
            glGetQueryObjectiv(queries_[slot * 2 + 1], GL_QUERY_RESULT_AVAILABLE, &available);
            if (!available) continue;
        }
        GLuint64 start = 0, end = 0;
        glGetQueryObjectui64v(queries_[slot * 2], GL_QUERY_RESULT, &start);
        glGetQueryObjectui64v(queries_[slot * 2 + 1], GL_QUERY_RESULT, &end);
        gpu_ns_[pending.frame] = end >= start ? static_cast<double>(end - start) : std::nan("");
        pending.active = false;
    }
}

void FrameTimer::begin(Uint64 now, double position, std::int64_t queued_frames) {
    const auto frame = begin_ns_.size();
    if (settling_ >= 0 && position >= seeks_[settling_]["to"].asDouble() + settle_advance_seconds) {
        auto& seek = seeks_[settling_];
        seek["settle_ns"] = Json::Int64(now - origin_ - seek["requested_ns"].asInt64());
        seek["settle_frame"] = Json::UInt64(frame);
        presenting_ = settling_;
        settling_ = -1;
    }
    begin_ns_.push_back(now - origin_);
    position_.push_back(position);
    queued_.push_back(queued_frames);
    gpu_ns_.push_back(std::nan(""));
    collect(false);
    const auto slot = next_query_ % ring;
    // Every slot in flight means the GPU is ring frames behind: wait for it.
    if (pending_[slot].active) collect(true);
    glQueryCounter(queries_[slot * 2], GL_TIMESTAMP);
    pending_[slot] = {frame, true};
}

void FrameTimer::drawn(Uint64 now) {
    glQueryCounter(queries_[(next_query_ % ring) * 2 + 1], GL_TIMESTAMP);
    ++next_query_;
    draw_ns_.push_back(now - origin_);
}

void FrameTimer::swapped(Uint64 now) {
    swap_ns_.push_back(now - origin_);
    if (presenting_ >= 0) {
        auto& seek = seeks_[presenting_];
        seek["present_ns"] = Json::Int64(now - origin_ - seek["requested_ns"].asInt64());
        presenting_ = -1;
    }
}

void FrameTimer::seek(Uint64 requested, Uint64 returned, double from, double to) {
    Json::Value seek;
    seek["requested_ns"] = Json::Int64(requested - origin_);
    seek["call_ns"] = Json::Int64(returned - requested);
    seek["frame"] = Json::UInt64(begin_ns_.size());
    seek["from"] = from;
    seek["to"] = to;
    seek["settle_ns"] = Json::nullValue;
    seek["settle_frame"] = Json::nullValue;
    seek["present_ns"] = Json::nullValue;
    seeks_.append(seek);
    // An unsettled earlier seek stays null: the newer seek superseded it.
    settling_ = static_cast<int>(seeks_.size()) - 1;
    presenting_ = -1;
}

void FrameTimer::write(const std::filesystem::path& path, Json::Value context) {
    collect(true);
    const auto frames = swap_ns_.size();
    Json::Value columns;
    for (std::size_t i = 0; i < frames; ++i) {
        columns["begin_ns"].append(Json::UInt64(begin_ns_[i]));
        columns["draw_ns"].append(Json::UInt64(draw_ns_[i]));
        columns["swap_ns"].append(Json::UInt64(swap_ns_[i]));
        columns["gpu_ns"].append(std::isfinite(gpu_ns_[i]) ? Json::Value(Json::UInt64(gpu_ns_[i])) : Json::Value());
        columns["position"].append(position_[i]);
        columns["queued_frames"].append(Json::Int64(queued_[i]));
    }
    context["kind"] = "harmonic.frame-report.v1";
    context["frame_count"] = Json::UInt64(frames);
    context["frames"] = frames ? columns : Json::Value(Json::objectValue);
    context["seeks"] = seeks_;
    context["settle_advance_seconds"] = settle_advance_seconds;
    const auto temporary = std::filesystem::path(path.string() + ".tmp");
    {
        std::ofstream output(temporary);
        if (!output) throw std::runtime_error("Cannot write frame report: " + path.string());
        Json::StreamWriterBuilder writer;
        writer["indentation"] = "";
        output << Json::writeString(writer, context) << '\n';
        if (!output) throw std::runtime_error("Cannot write frame report: " + path.string());
    }
    std::filesystem::rename(temporary, path);
}
} // namespace harmonic
