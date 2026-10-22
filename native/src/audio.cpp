#include "harmonic.hpp"

extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/channel_layout.h>
#include <libavutil/mem.h>
#include <libavutil/sha.h>
#include <libswresample/swresample.h>
}

#include <algorithm>
#include <array>
#include <fstream>
#include <iomanip>
#include <memory>
#include <sstream>
#include <stdexcept>

namespace harmonic {
namespace {
void check(int status, const char* operation) {
    if (status < 0) {
        char message[AV_ERROR_MAX_STRING_SIZE];
        av_strerror(status, message, sizeof(message));
        throw std::runtime_error(std::string(operation) + ": " + message);
    }
}
struct FormatCloser { void operator()(AVFormatContext* p) const { avformat_close_input(&p); } };
struct CodecCloser { void operator()(AVCodecContext* p) const { avcodec_free_context(&p); } };
struct FrameCloser { void operator()(AVFrame* p) const { av_frame_free(&p); } };
struct PacketCloser { void operator()(AVPacket* p) const { av_packet_free(&p); } };
struct ResamplerCloser { void operator()(SwrContext* p) const { swr_free(&p); } };
struct ShaCloser { void operator()(AVSHA* p) const { av_free(p); } };
std::unique_ptr<AVSHA, ShaCloser> make_digest() {
    std::unique_ptr<AVSHA, ShaCloser> digest(av_sha_alloc());
    if (!digest) throw std::bad_alloc();
    check(av_sha_init(digest.get(), 256), "Initialize checksum");
    return digest;
}
std::string finish_digest(AVSHA* digest) {
    std::array<std::uint8_t, 32> bytes{};
    av_sha_final(digest, bytes.data());
    std::ostringstream text;
    for (auto byte : bytes) text << std::hex << std::setfill('0') << std::setw(2) << unsigned(byte);
    return text.str();
}
} // namespace

std::string sha256(const void* data, std::size_t bytes) {
    auto digest = make_digest();
    const auto* cursor = static_cast<const std::uint8_t*>(data);
    while (bytes) {
        const auto size = std::min<std::size_t>(bytes, 1024 * 1024);
        av_sha_update(digest.get(), cursor, size);
        cursor += size;
        bytes -= size;
    }
    return finish_digest(digest.get());
}

std::string sha256_file(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("Cannot read " + path.string());
    auto digest = make_digest();
    std::array<char, 65536> block{};
    while (input.read(block.data(), block.size()) || input.gcount())
        av_sha_update(digest.get(), reinterpret_cast<const std::uint8_t*>(block.data()), input.gcount());
    if (!input.eof()) throw std::runtime_error("Error reading " + path.string());
    return finish_digest(digest.get());
}

std::vector<float> decode_audio(const std::filesystem::path& path) {
    AVFormatContext* raw_format = nullptr;
    check(avformat_open_input(&raw_format, path.c_str(), nullptr, nullptr), "Open audio");
    std::unique_ptr<AVFormatContext, FormatCloser> format(raw_format);
    check(avformat_find_stream_info(format.get(), nullptr), "Read audio streams");
    // Match the analyzer's explicit 0:a:0 selection, not FFmpeg's best-stream heuristic.
    int stream_index = -1;
    for (unsigned i = 0; i < format->nb_streams; ++i) {
        if (format->streams[i]->codecpar->codec_type == AVMEDIA_TYPE_AUDIO) {
            stream_index = static_cast<int>(i);
            break;
        }
    }
    if (stream_index < 0) throw std::runtime_error("The file has no audio stream");
    auto* parameters = format->streams[stream_index]->codecpar;
    auto* decoder = avcodec_find_decoder(parameters->codec_id);
    if (!decoder) throw std::runtime_error("No decoder for this audio format");
    std::unique_ptr<AVCodecContext, CodecCloser> codec(avcodec_alloc_context3(decoder));
    if (!codec) throw std::bad_alloc();
    check(avcodec_parameters_to_context(codec.get(), parameters), "Configure decoder");
    codec->pkt_timebase = format->streams[stream_index]->time_base;
    check(avcodec_open2(codec.get(), decoder, nullptr), "Start decoder");
    if (codec->sample_rate <= 0 || codec->ch_layout.nb_channels <= 0)
        throw std::runtime_error("Invalid source sample rate/channel layout");

    AVChannelLayout stereo = AV_CHANNEL_LAYOUT_STEREO;
    SwrContext* raw_resampler = nullptr;
    check(swr_alloc_set_opts2(&raw_resampler, &stereo, AV_SAMPLE_FMT_FLT, sample_rate,
        &codec->ch_layout, codec->sample_fmt, codec->sample_rate, 0, nullptr), "Configure resampler");
    std::unique_ptr<SwrContext, ResamplerCloser> resampler(raw_resampler);
    check(swr_init(resampler.get()), "Start resampler");
    std::unique_ptr<AVFrame, FrameCloser> frame(av_frame_alloc());
    std::unique_ptr<AVPacket, PacketCloser> packet(av_packet_alloc());
    if (!frame || !packet) throw std::bad_alloc();
    std::vector<float> samples;
    auto convert = [&](const std::uint8_t** input, int count) {
        const int capacity = swr_get_out_samples(resampler.get(), count);
        check(capacity, "Size resampling buffer");
        std::vector<float> output(static_cast<std::size_t>(capacity) * channels);
        auto* destination = reinterpret_cast<std::uint8_t*>(output.data());
        const int written = swr_convert(resampler.get(), &destination, capacity, input, count);
        check(written, "Resample audio");
        samples.insert(samples.end(), output.begin(), output.begin() + written * channels);
        return written;
    };
    auto receive = [&] {
        while (true) {
            const int status = avcodec_receive_frame(codec.get(), frame.get());
            if (status == AVERROR(EAGAIN) || status == AVERROR_EOF) break;
            check(status, "Decode audio frame");
            convert(const_cast<const std::uint8_t**>(frame->extended_data), frame->nb_samples);
            av_frame_unref(frame.get());
        }
    };
    while (true) {
        const int status = av_read_frame(format.get(), packet.get());
        if (status == AVERROR_EOF) break;
        check(status, "Read audio packet");
        if (packet->stream_index == stream_index) {
            check(avcodec_send_packet(codec.get(), packet.get()), "Queue audio packet");
            receive();
        }
        av_packet_unref(packet.get());
    }
    check(avcodec_send_packet(codec.get(), nullptr), "Flush audio decoder");
    receive();
    while (convert(nullptr, 0) > 0) {}
    if (samples.empty()) throw std::runtime_error("The audio decoded to zero frames");
    return samples;
}
} // namespace harmonic
