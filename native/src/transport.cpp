#include "harmonic.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace harmonic {
namespace {
void check(bool result, const char* operation) {
    if (!result) throw std::runtime_error(std::string(operation) + ": " + SDL_GetError());
}
class Lock {
public:
    explicit Lock(SDL_AudioStream* stream) : stream_(stream) { check(SDL_LockAudioStream(stream_), "Lock audio"); }
    ~Lock() { SDL_UnlockAudioStream(stream_); }
private:
    SDL_AudioStream* stream_;
};
} // namespace

Transport::Transport(const std::vector<float>& audio) : audio_(audio) {
    SDL_AudioSpec spec{SDL_AUDIO_F32, channels, sample_rate};
    stream_ = SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK, &spec, callback, this);
    if (!stream_) throw std::runtime_error(std::string("Open audio output: ") + SDL_GetError());
    SDL_AudioSpec device{};
    int frames = 0;
    if (SDL_GetAudioDeviceFormat(SDL_GetAudioStreamDevice(stream_), &device, &frames) && device.freq > 0)
        buffer_seconds_ = static_cast<double>(frames) / device.freq;
    anchor_ticks_ = SDL_GetTicksNS();
}

Transport::~Transport() { if (stream_) SDL_DestroyAudioStream(stream_); }

void SDLCALL Transport::callback(void* userdata, SDL_AudioStream* stream, int additional, int) {
    auto& self = *static_cast<Transport*>(userdata);
    if (additional <= 0 || !self.callback_error_.empty()) return;
    constexpr int bytes_per_frame = sizeof(float) * channels;
    const auto requested = static_cast<std::size_t>((additional + bytes_per_frame - 1) / bytes_per_frame);
    const auto count = std::min(requested, self.audio_.size() / channels - self.cursor_);
    if (count) {
        if (!SDL_PutAudioStreamData(stream, self.audio_.data() + self.cursor_ * channels,
                                   static_cast<int>(count * bytes_per_frame))) {
            self.callback_error_ = SDL_GetError();
            return;
        }
        self.cursor_ += count;
        // Timestamp delivery on the device thread, not when the UI next asks
        // for a position. This also lets the last chunk finish after EOF.
        self.anchor_frame_ = std::max(self.seek_floor_, self.cursor_ - self.buffer_seconds_ * sample_rate);
        self.anchor_ticks_ = SDL_GetTicksNS();
    }
    if (self.cursor_ == self.audio_.size() / channels && !self.flushed_) {
        if (!SDL_FlushAudioStream(stream)) self.callback_error_ = SDL_GetError();
        self.flushed_ = true;
    }
}

double Transport::position_locked() {
    if (paused_) return held_frame_;
    const int queued = SDL_GetAudioStreamQueued(stream_);
    check(queued >= 0, "Read audio position");
    constexpr std::int64_t bytes_per_frame = sizeof(float) * channels;
    const auto queued_frames = static_cast<std::int64_t>(queued) / bytes_per_frame;
    const auto consumed = static_cast<std::int64_t>(cursor_) - queued_frames;
    const auto now = SDL_GetTicksNS();
    const double estimate = anchor_frame_ + static_cast<double>(now - anchor_ticks_) * sample_rate / 1e9;
    const double upper = std::min<double>(consumed, audio_.size() / channels);
    last_frame_ = std::clamp(std::max(last_frame_, estimate), seek_floor_, std::max(seek_floor_, upper));
    return last_frame_;
}

double Transport::position() {
    Lock lock(stream_);
    return position_locked() / sample_rate;
}

void Transport::reset_locked(double frame) {
    check(SDL_ClearAudioStream(stream_), "Clear audio queue");
    cursor_ = static_cast<std::size_t>(std::clamp(std::round(frame), 0.0, static_cast<double>(audio_.size() / channels)));
    held_frame_ = last_frame_ = seek_floor_ = anchor_frame_ = static_cast<double>(cursor_);
    anchor_ticks_ = SDL_GetTicksNS();
    flushed_ = false;
}

void Transport::pause() {
    if (paused_) return;
    // Device APIs acquire the device lock: call them outside the stream lock.
    check(SDL_PauseAudioStreamDevice(stream_), "Pause audio");
    Lock lock(stream_);
    const double frame = position_locked();
    paused_ = true;
    reset_locked(frame);
}

void Transport::resume() {
    if (!paused_) return;
    {
        Lock lock(stream_);
        paused_ = false;
        anchor_ticks_ = SDL_GetTicksNS();
    }
    check(SDL_ResumeAudioStreamDevice(stream_), "Resume audio");
}

void Transport::seek(double seconds) {
    if (!std::isfinite(seconds)) throw std::runtime_error("Seek position must be finite");
    const bool was_playing = !paused_;
    check(SDL_PauseAudioStreamDevice(stream_), "Pause for seek");
    {
        Lock lock(stream_);
        reset_locked(seconds * sample_rate);
    }
    if (was_playing) check(SDL_ResumeAudioStreamDevice(stream_), "Resume after seek");
}

std::string Transport::error() {
    Lock lock(stream_);
    return callback_error_;
}
} // namespace harmonic
