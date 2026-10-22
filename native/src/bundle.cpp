#include "harmonic.hpp"

#include <arrow/api.h>
#include <arrow/io/api.h>
#include <arrow/ipc/api.h>

#include <algorithm>
#include <cmath>
#include <fstream>
#include <stdexcept>

namespace harmonic {
namespace {
template<class T> T unwrap(arrow::Result<T> result) {
    if (!result.ok()) throw std::runtime_error("Arrow: " + result.status().ToString());
    return std::move(result).ValueOrDie();
}
void require(bool value, const std::string& message) {
    if (!value) throw std::runtime_error("Invalid analysis bundle: " + message);
}
std::shared_ptr<arrow::Array> column(const std::shared_ptr<arrow::Table>& table,
                                   const std::string& name, arrow::Type::type type) {
    auto values = table->GetColumnByName(name);
    require(values && values->type()->id() == type && values->null_count() == 0, "bad " + name + " column");
    require(values->num_chunks() == 1, "unexpected chunks in " + name);
    return values->chunk(0);
}
std::vector<float> floats(const std::shared_ptr<arrow::Table>& table, const char* name) {
    auto values = std::static_pointer_cast<arrow::FloatArray>(column(table, name, arrow::Type::FLOAT));
    std::vector<float> result(values->raw_values(), values->raw_values() + values->length());
    for (float value : result) require(std::isfinite(value) && value >= 0, std::string("invalid ") + name + " value");
    return result;
}
} // namespace

Bundle load_bundle(const std::filesystem::path& path, const std::filesystem::path& audio_override) {
    const auto manifest_path = std::filesystem::is_directory(path) ? path / "manifest.json" : path;
    std::ifstream input(manifest_path);
    if (!input) throw std::runtime_error("Cannot open manifest: " + manifest_path.string());
    Bundle bundle;
    input >> bundle.manifest;
    const auto& m = bundle.manifest;
    require(m["schema_version"].isInt() && m["schema_version"].asInt() == 1, "unsupported schema version");
    require(m["pipeline"].asString() == "harmonic.mix.v1", "unsupported pipeline");
    require(m["audio"]["sample_rate"].asInt() == sample_rate && m["audio"]["channels"].asInt() == channels,
            "expected 48 kHz stereo");
    require(m["audio"]["sample_count"].isInt64(), "missing sample count");
    bundle.sample_count = m["audio"]["sample_count"].asInt64();
    require(bundle.sample_count > 0, "empty audio");
    bundle.hop = m["analysis"]["hop_size"].asInt();
    require(bundle.hop > 0 && m["analysis"]["frame_offset_samples"].asInt64() == 0, "invalid timebase");
    require(m["streams"].isArray() && m["streams"].size() == 1, "expected a single mix stream");
    const auto& stream = m["streams"][0];
    require(stream["name"].asString() == "mix", "expected mix stream");
    bundle.bands = stream["bands"].asInt();
    require(bundle.bands > 0 && bundle.bands <= 1024, "invalid band count");
    const auto relative_artifact = std::filesystem::path(stream["artifact"].asString());
    require(relative_artifact == "mix.arrow", "unexpected artifact path");
    const auto artifact = manifest_path.parent_path() / relative_artifact;
    require(sha256_file(artifact) == stream["sha256"].asString(), "feature checksum mismatch");
    bundle.audio_path = audio_override.empty() ? std::filesystem::path(m["source"]["path"].asString()) : audio_override;
    require(sha256_file(bundle.audio_path) == m["source"]["sha256"].asString(), "audio checksum mismatch; analyze this recording again");

    auto file = unwrap(arrow::io::ReadableFile::Open(artifact.string()));
    auto reader = unwrap(arrow::ipc::RecordBatchFileReader::Open(file));
    std::vector<std::shared_ptr<arrow::RecordBatch>> batches;
    for (int i = 0; i < reader->num_record_batches(); ++i) batches.push_back(unwrap(reader->ReadRecordBatch(i)));
    auto table = unwrap(arrow::Table::FromRecordBatches(batches));
    const auto status = table->ValidateFull();
    require(status.ok(), status.ToString());
    table = unwrap(table->CombineChunks());
    const auto frames = (bundle.sample_count - 1) / bundle.hop + 1;
    require(table->num_rows() == frames && stream["frames"].asInt64() == frames, "frame count does not match audio timebase");
    auto indices = std::static_pointer_cast<arrow::Int64Array>(column(table, "sample_index", arrow::Type::INT64));
    for (std::int64_t i = 0; i < frames; ++i) require(indices->Value(i) == i * bundle.hop, "nonuniform sample indices");
    bundle.rms = floats(table, "rms");
    bundle.peak = floats(table, "peak");
    bundle.onset = floats(table, "onset");
    auto spectrum = std::static_pointer_cast<arrow::FixedSizeListArray>(column(table, "spectrum", arrow::Type::FIXED_SIZE_LIST));
    require(spectrum->value_type()->id() == arrow::Type::FLOAT && spectrum->value_length() == bundle.bands,
            "invalid spectrum shape");
    auto values = std::static_pointer_cast<arrow::FloatArray>(spectrum->values());
    require(values->null_count() == 0, "null spectrum values");
    bundle.spectrum.reserve(static_cast<std::size_t>(frames) * bundle.bands);
    for (std::int64_t i = 0; i < frames; ++i) {
        const float* row = values->raw_values() + spectrum->value_offset(i);
        for (int band = 0; band < bundle.bands; ++band) {
            require(std::isfinite(row[band]) && row[band] >= 0, "invalid spectrum value");
            bundle.spectrum.push_back(row[band]);
        }
    }
    const auto& edges = m["analysis"]["band_edges_hz"];
    require(edges.isArray() && edges.size() == static_cast<unsigned>(bundle.bands + 1), "missing band edges");
    for (const auto& edge : edges) {
        const float value = edge.asFloat();
        require(std::isfinite(value) && value > 0 && (bundle.band_edges.empty() || value > bundle.band_edges.back()), "invalid band edges");
        bundle.band_edges.push_back(value);
    }
    bundle.rms_scale = std::max(1e-6f, stream["stats"]["rms"]["p99"].asFloat());
    bundle.onset_scale = std::max(1e-6f, stream["stats"]["onset"]["p99"].asFloat());
    bundle.spectrum_top_db = std::max(-80.0f, 20 * std::log10(std::max(1e-6f, stream["stats"]["spectrum"]["p99"].asFloat())));
    return bundle;
}

float Bundle::interpolate(const std::vector<float>& values, double seconds) const {
    const double frame = std::clamp(seconds * sample_rate / hop, 0.0, static_cast<double>(values.size() - 1));
    const auto a = static_cast<std::size_t>(frame), b = std::min(a + 1, values.size() - 1);
    return std::lerp(values[a], values[b], static_cast<float>(frame - a));
}

std::vector<float> Bundle::spectrum_at(double seconds) const {
    const double frame = std::clamp(seconds * sample_rate / hop, 0.0, static_cast<double>(rms.size() - 1));
    const auto a = static_cast<std::size_t>(frame), b = std::min(a + 1, rms.size() - 1);
    std::vector<float> result(bands);
    for (int i = 0; i < bands; ++i)
        result[i] = std::lerp(spectrum[a * bands + i], spectrum[b * bands + i], static_cast<float>(frame - a));
    return result;
}
} // namespace harmonic
