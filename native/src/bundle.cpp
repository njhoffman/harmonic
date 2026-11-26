#include "harmonic.hpp"

#include <arrow/api.h>
#include <arrow/io/api.h>
#include <arrow/ipc/api.h>

#include <algorithm>
#include <cmath>
#include <fstream>
#include <stdexcept>
#include <regex>
#include <set>
#include <sstream>

namespace harmonic {
namespace {
template<class T> T unwrap(arrow::Result<T> result) {
    if (!result.ok()) throw std::runtime_error("Arrow: " + result.status().ToString());
    return std::move(result).ValueOrDie();
}
void require(bool value, const std::string& message) {
    if (!value) throw std::runtime_error("Invalid analysis bundle: " + message);
}
bool json_integer(const Json::Value& value) {
    return value.type() == Json::intValue || value.type() == Json::uintValue;
}
bool valid_level(const Json::Value& value) {
    return value.isNumeric() && std::isfinite(value.asDouble()) && value.asDouble() >= 0;
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
FeatureStream read_features(const std::filesystem::path& artifact, const Json::Value& stream,
                            std::int64_t start, std::int64_t count, int hop, int version) {
    FeatureStream features;
    features.name = stream["name"].asString();
    features.start_sample = start;
    features.sample_count = count;
    features.hop = hop;
    features.bands = stream["bands"].asInt();
    auto file = unwrap(arrow::io::ReadableFile::Open(artifact.string()));
    auto reader = unwrap(arrow::ipc::RecordBatchFileReader::Open(file));
    std::vector<std::shared_ptr<arrow::RecordBatch>> batches;
    for (int i = 0; i < reader->num_record_batches(); ++i) batches.push_back(unwrap(reader->ReadRecordBatch(i)));
    auto table = unwrap(arrow::Table::FromRecordBatches(batches));
    auto metadata = table->schema()->metadata();
    require(metadata && unwrap(metadata->Get("harmonic.schema_version")) == std::to_string(version) &&
            unwrap(metadata->Get("harmonic.stream")) == features.name, "feature metadata mismatch");
    require(table->num_columns() == 5, "invalid feature columns");
    const auto status = table->ValidateFull();
    require(status.ok(), status.ToString());
    table = unwrap(table->CombineChunks());
    const auto frames = (count - 1) / hop + 1;
    require(table->num_rows() == frames && stream["frames"].asInt64() == frames, "frame count does not match audio timebase");
    auto indices = std::static_pointer_cast<arrow::Int64Array>(column(table, "sample_index", arrow::Type::INT64));
    for (std::int64_t i = 0; i < frames; ++i) require(indices->Value(i) == start + i * hop, "nonuniform sample indices");
    features.rms = floats(table, "rms");
    features.peak = floats(table, "peak");
    features.onset = floats(table, "onset");
    auto spectrum = std::static_pointer_cast<arrow::FixedSizeListArray>(column(table, "spectrum", arrow::Type::FIXED_SIZE_LIST));
    require(spectrum->value_type()->id() == arrow::Type::FLOAT && spectrum->value_length() == stream["bands"].asInt(),
            "invalid spectrum shape");
    auto values = std::static_pointer_cast<arrow::FloatArray>(spectrum->values());
    require(values->null_count() == 0, "null spectrum values");
    features.spectrum.reserve(static_cast<std::size_t>(frames) * stream["bands"].asInt());
    for (std::int64_t i = 0; i < frames; ++i) {
        const float* row = values->raw_values() + spectrum->value_offset(i);
        for (int band = 0; band < stream["bands"].asInt(); ++band) {
            require(std::isfinite(row[band]) && row[band] >= 0, "invalid spectrum value");
            features.spectrum.push_back(row[band]);
        }
    }
    auto scale = [&](const char* field) {
        const auto& value = stream["stats"][field]["p99"];
        require(value.isNumeric() && std::isfinite(value.asDouble()) && value.asDouble() >= 0, "invalid feature scale");
        return std::max(1e-6f, value.asFloat());
    };
    features.rms_scale = scale("rms");
    features.onset_scale = scale("onset");
    features.spectrum_top_db = std::max(-80.0f, 20 * std::log10(scale("spectrum")));
    return features;
}
constexpr int presence_frame_samples = 1920;

PresenceStream read_presence(const std::filesystem::path& artifact, const Json::Value& stream,
                             std::int64_t start, std::int64_t count) {
    PresenceStream presence;
    presence.target = stream["target"].asString();
    presence.prompt = stream["prompt"].asString();
    presence.reliability = stream["reliability"].asString();
    presence.start_sample = start;
    presence.sample_count = count;
    presence.frame_samples = presence_frame_samples;
    auto file = unwrap(arrow::io::ReadableFile::Open(artifact.string()));
    auto reader = unwrap(arrow::ipc::RecordBatchFileReader::Open(file));
    std::vector<std::shared_ptr<arrow::RecordBatch>> batches;
    for (int i = 0; i < reader->num_record_batches(); ++i) batches.push_back(unwrap(reader->ReadRecordBatch(i)));
    auto table = unwrap(arrow::Table::FromRecordBatches(batches));
    auto metadata = table->schema()->metadata();
    require(metadata && unwrap(metadata->Get("harmonic.schema_version")) == "3" &&
            unwrap(metadata->Get("harmonic.stream")) == stream["name"].asString(), "presence metadata mismatch");
    require(table->num_columns() == 2 && table->ValidateFull().ok(), "invalid presence columns");
    table = unwrap(table->CombineChunks());
    const auto frames = (count + presence_frame_samples - 1) / presence_frame_samples;
    require(table->num_rows() == frames && stream["frames"].isInt64() && stream["frames"].asInt64() == frames,
            "presence frame count does not match coverage");
    auto indices = std::static_pointer_cast<arrow::Int64Array>(column(table, "sample_index", arrow::Type::INT64));
    for (std::int64_t i = 0; i < frames; ++i)
        require(indices->Value(i) == start + i * presence_frame_samples, "invalid presence sample indices");
    auto values = std::static_pointer_cast<arrow::FloatArray>(column(table, "probability", arrow::Type::FLOAT));
    presence.probability.assign(values->raw_values(), values->raw_values() + values->length());
    for (float value : presence.probability)
        require(std::isfinite(value) && value >= 0 && value <= 1, "invalid presence probability");
    require(sha256(presence.probability.data(), presence.probability.size() * sizeof(float)) ==
            stream["probabilities_sha256"].asString(), "presence values differ from the separation report");
    return presence;
}
} // namespace

Bundle load_bundle(const std::filesystem::path& path, const std::filesystem::path& audio_override) {
    const auto manifest_path = std::filesystem::is_directory(path) ? path / "manifest.json" : path;
    std::ifstream input(manifest_path);
    if (!input) throw std::runtime_error("Cannot open manifest: " + manifest_path.string());
    Bundle bundle;
    input >> bundle.manifest;
    const auto& m = bundle.manifest;
    require(m["schema_version"].isInt(), "unsupported schema version");
    const int version = m["schema_version"].asInt();
    require((version == 1 && m["pipeline"].asString() == "harmonic.mix.v1") ||
            (version == 2 && m["pipeline"].asString() == "harmonic.sam.features.v1") ||
            (version == 3 && m["pipeline"].asString() == "harmonic.sam.features.v2"), "unsupported schema or pipeline");
    require(m["audio"]["sample_rate"].asInt() == sample_rate && m["audio"]["channels"].asInt() == channels,
            "expected 48 kHz stereo");
    require(m["audio"]["sample_count"].isInt64(), "missing sample count");
    bundle.sample_count = m["audio"]["sample_count"].asInt64();
    require(bundle.sample_count > 0, "empty audio");
    bundle.hop = m["analysis"]["hop_size"].asInt();
    require(bundle.hop > 0 && m["analysis"]["frame_offset_samples"].asInt64() == 0, "invalid timebase");
    require(m["streams"].isArray() && !m["streams"].empty() &&
            (version >= 2 || m["streams"].size() == 1), "expected a single mix stream");
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

    static_cast<FeatureStream&>(bundle) = read_features(artifact, stream, 0, bundle.sample_count, bundle.hop, 1);
    const auto& edges = m["analysis"]["band_edges_hz"];
    require(edges.isArray() && edges.size() == static_cast<unsigned>(bundle.bands + 1), "missing band edges");
    for (const auto& edge : edges) {
        const float value = edge.asFloat();
        require(std::isfinite(value) && value > 0 && (bundle.band_edges.empty() || value > bundle.band_edges.back()), "invalid band edges");
        bundle.band_edges.push_back(value);
    }
    if (version >= 2) {
        require(bundle.hop == 960 && bundle.bands == 64 && m["analysis"]["window_size"].asInt() == 4096 &&
                m["analysis"]["window"].asString() == "hann_symmetric" &&
                m["analysis"]["padding"].asString() == "zeros_centered" &&
                m["analysis"]["spectrum_scale"].asString() == "linear_rms_amplitude" &&
                m["analysis"]["channel_reduction"].asString() == "mean_power", "unsupported source feature configuration");
        require(m["separation"]["artifact"].asString() == "sam-report.json", "unexpected separation report path");
        const auto report_path = manifest_path.parent_path() / "sam-report.json";
        require(sha256_file(report_path) == m["separation"]["sha256"].asString(), "separation report checksum mismatch");
        Json::Value report;
        std::ifstream report_input(report_path);
        report_input >> report;
        const bool song = report["kind"].asString() == "harmonic.sam-audio-song-result.v1";
        require(report["schema_version"].asInt() == 1 &&
                (song || report["kind"].asString() == "harmonic.sam-audio-result.v1") &&
                report["sample_rate"].asInt() == sample_rate && report["channels"].asInt() == 1,
                "unsupported separation provenance");
        require(report["source"]["sha256"] == m["source"]["sha256"] &&
                report["source"]["pcm_sha256"] == m["source"]["pcm_sha256"] &&
                report["source"]["sample_count"].asInt64() == bundle.sample_count, "separation source identity mismatch");
        require(report["start_sample"].isInt64() && report["sample_count"].isInt64(), "invalid separation coverage");
        const auto start = report["start_sample"].asInt64(), count = report["sample_count"].asInt64();
        require(start >= 0 && start < bundle.sample_count && count > 0 && (song || count <= 30 * sample_rate) &&
                count <= bundle.sample_count - start, "invalid separation coverage");
        require(report["semantics"].asString() == "independent_prompted_target_and_residual_pairs; targets_may_overlap" &&
                report["channel_reduction"].asString() == "arithmetic_mean_to_mono; no_gain_normalization" &&
                report["anchors"].isNull(), "unsupported separation semantics");
        require(report["model"]["id"].asString() == "facebook/sam-audio-large-tv" &&
                report["model"]["revision"].asString() == "b9fc94687ec044c570cbe30b8c28100cd056f1cb" &&
                report["model"]["source_revision"].asString() == "bb4c6999d2677c7402360e426afc01ddfad6dce0",
                "unsupported separation model");
        const auto& settings = report["settings"];
        require(settings["dtype"].asString() == "float32" && settings["ode_method"].asString() == "midpoint" &&
                settings["ode_step_size"].asDouble() == 0.0625 && settings["predict_spans"].isBool() &&
                !settings["predict_spans"].asBool() && settings["reranking_candidates"].asInt() == 1,
                "unsupported separation settings");
        const auto& presence_model = report["presence_model"];
        const bool measured = !presence_model.isNull();
        require(version == 3 || !measured, "schema-2 bundles cannot carry presence");
        if (version == 3) {
            const auto& presence = m["presence"];
            require(m.isMember("presence") && presence.isNull() == !measured, "presence provenance mismatch");
            if (measured)
                require(presence_model["id"].asString() == "facebook/pe-a-frame-large" &&
                        presence_model["revision"].asString() == "40187271298f84e2966d4518c88dde698540c9ad" &&
                        presence_model["frame_samples"].isInt() &&
                        presence_model["frame_samples"].asInt() == presence_frame_samples &&
                        presence["model"]["id"] == presence_model["id"] &&
                        presence["model"]["revision"] == presence_model["revision"] &&
                        presence["frame_samples"] == presence_model["frame_samples"] &&
                        presence["frame_alignment"].asString() == "frame_start_half_open" &&
                        presence["values"].asString() == "probability_no_threshold", "unsupported presence provenance");
        }
        require(report["pairs"].isObject() && report["pairs"].size() >= 1 && report["pairs"].size() <= 8 &&
                m["streams"].size() == 1 + report["pairs"].size() * (measured ? 3 : 2), "separation stream set mismatch");
        for (int i = 0; i <= bundle.bands; ++i) {
            const double expected = 20.0 * std::pow(1200.0, static_cast<double>(i) / bundle.bands);
            require(std::abs(edges[i].asDouble() - expected) <= expected * 1e-9, "unsupported frequency bands");
        }
        const auto& extraction = m["feature_extraction"];
        require(extraction["gain_correction"].asString() == "none" &&
                extraction["latency_correction_samples"].isInt64() && extraction["latency_correction_samples"].asInt64() == 0,
                "invalid feature extraction corrections");
        const std::regex hash_pattern("[0-9a-f]{64}"), revision_pattern("[0-9a-f]{40}");
        for (const auto* key : {"code_sha256", "mix_manifest_sha256"})
            require(std::regex_match(extraction[key].asString(), hash_pattern), "invalid feature extraction provenance");
        for (const auto* key : {"app_version", "numpy_version", "pyarrow_version"})
            require(!extraction[key].asString().empty(), "missing feature extraction version");
        for (const auto* key : {"job_sha256", "worker_code_sha256", "worker_lock_sha256"})
            require(std::regex_match(report[key].asString(), hash_pattern), "invalid separation checksum provenance");
        for (const auto* key : {"config.json", "checkpoint.pt", "LICENSE"})
            require(std::regex_match(report["model"]["files_sha256"][key].asString(), hash_pattern), "missing model hash");
        require(!report["auxiliary_text_model"]["id"].asString().empty() &&
                std::regex_match(report["auxiliary_text_model"]["revision"].asString(), revision_pattern),
                "invalid auxiliary model provenance");
        require(report["seed"].isUInt64() && report["seed"].asUInt64() < (1ULL << 32) &&
                report["codec_hop_samples"].isInt() && report["codec_hop_samples"].asInt() > 0 &&
                report["codec_hop_samples"].asInt() <= sample_rate, "invalid seed or codec hop");
        if (song) {
            const Json::Value& song_report = report;
            const auto& run_binding = song_report["run_binding_sha256"];
            require(!report.isMember("run_binding_sha256") ||
                    (run_binding.isString() && std::regex_match(run_binding.asString(), hash_pattern)),
                    "invalid song run binding hash");
            require(start == 0 && count == bundle.sample_count, "invalid full-song coverage");
            const auto& chunking = report["chunking"];
            require(chunking["chunk_samples"].isInt() && chunking["overlap_samples"].isInt(), "invalid chunk sizes");
            const int chunk = chunking["chunk_samples"].asInt(), overlap = chunking["overlap_samples"].asInt();
            require(chunk > 0 && chunk <= 30 * sample_rate && overlap > 0 && overlap < chunk / 2.0 &&
                    chunking["blend"].asString() == "half_cosine_complementary_v1" &&
                    chunking["plan_sha256"] == report["job_sha256"] && chunking["chunks"].isArray(),
                    "unsupported full-song overlap policy");
            std::int64_t expected_start = 0;
            Json::ArrayIndex index = 0;
            while (true) {
                require(index < chunking["chunks"].size(), "missing chunk provenance");
                const auto& item = chunking["chunks"][index];
                const auto raw = item["report_json"].asString();
                require(json_integer(item["index"]) &&
                        item["index"].isUInt() && item["index"].asUInt() == index, "invalid retained chunk index");
                require(sha256(raw.data(), raw.size()) == item["report_sha256"].asString(),
                        "retained chunk report checksum mismatch");
                Json::Value child;
                std::istringstream child_input(raw);
                child_input >> child;
                const auto n = std::min<std::int64_t>(chunk, count - expected_start);
                require(child["kind"].asString() == "harmonic.sam-audio-result.v1" && child["schema_version"].asInt() == 1 &&
                        child["start_sample"].asInt64() == expected_start && child["sample_count"].asInt64() == n &&
                        child["job_sha256"] == item["job_sha256"] &&
                        std::regex_match(child["job_sha256"].asString(), hash_pattern) &&
                        child["sample_rate"].asInt() == sample_rate && child["channels"].asInt() == 1 &&
                        child["pairs"].isObject() && child["pairs"].getMemberNames() == report["pairs"].getMemberNames(),
                        "invalid retained chunk timebase/targets");
                for (const auto* key : {"source", "model", "auxiliary_text_model", "normalized_config_sha256", "settings",
                                       "seed", "semantics", "channel_reduction", "anchors", "codec_hop_samples",
                                       "worker_code_sha256", "worker_lock_sha256"})
                    require(child[key] == report[key], "inconsistent retained chunk provenance");
                require(child["presence_model"] == presence_model, "inconsistent retained chunk presence model");
                require(child.isMember("run_binding_sha256") == report.isMember("run_binding_sha256") &&
                        child["run_binding_sha256"] == run_binding, "inconsistent retained chunk run binding");
                for (const auto& target : report["pairs"].getMemberNames()) {
                    const auto& pair = child["pairs"][target];
                    require(pair["description"] == report["pairs"][target]["description"],
                            "inconsistent retained chunk prompt");
                    require(valid_level(pair["sum_error_rms"]), "invalid retained chunk reconstruction level");
                    for (const auto* role : {"target", "residual"}) {
                        const auto& wave = pair[role];
                        const auto& raw_count = wave["raw_sample_count"];
                        const auto& trim = wave["right_trim_samples"];
                        require(wave["artifact"].asString() == target + "-" + role + ".wav" &&
                                json_integer(wave["sample_count"]) && wave["sample_count"].asInt64() == n &&
                                std::regex_match(wave["sha256"].asString(), hash_pattern) &&
                                json_integer(trim) && trim.isInt64() && trim.asInt64() >= 0 &&
                                trim.asInt64() < report["codec_hop_samples"].asInt() &&
                                json_integer(raw_count) && raw_count.isInt64() && raw_count.asInt64() == n + trim.asInt64() &&
                                valid_level(wave["rms"]) && valid_level(wave["peak"]), "invalid retained chunk waveform");
                    }
                }
                ++index;
                if (expected_start + chunk >= count) break;
                expected_start += chunk - overlap;
            }
            require(index == chunking["chunks"].size(), "unexpected extra chunk provenance");
        }
        std::set<std::string> seen;
        for (Json::ArrayIndex i = 1; i < m["streams"].size(); ++i) {
            const auto& item = m["streams"][i];
            const auto target = item["target"].asString(), role = item["role"].asString();
            require(std::regex_match(target, std::regex("[a-z][a-z0-9_-]{0,31}")) &&
                    (role == "target" || role == "residual" || (measured && role == "presence")) &&
                    report["pairs"].isMember(target), "invalid source role/target");
            const auto name = "sam." + target + "." + role;
            if (role == "presence") {
                const auto filename = "sam-" + target + "-presence.arrow";
                const auto& pair = report["pairs"][target];
                const auto reliability = item["reliability"].asString();
                require(item["name"].asString() == name && item["artifact"].asString() == filename &&
                        seen.insert(name).second, "invalid or duplicate presence artifact");
                require(item["start_sample"].isInt64() && item["sample_count"].isInt64() &&
                        item["start_sample"].asInt64() == start && item["sample_count"].asInt64() == count &&
                        item["frame_samples"].isInt() && item["frame_samples"].asInt() == presence_frame_samples &&
                        item["prompt"] == pair["description"] &&
                        item["probabilities_sha256"] == pair["presence"]["sha256"] &&
                        std::regex_match(item["probabilities_sha256"].asString(), hash_pattern) &&
                        (reliability == "benchmarked" || reliability == "low_confidence" || reliability == "unbenchmarked"),
                        "presence stream provenance mismatch");
                const auto artifact_path = manifest_path.parent_path() / filename;
                require(sha256_file(artifact_path) == item["sha256"].asString(), "presence checksum mismatch");
                bundle.presence.push_back(read_presence(artifact_path, item, start, count));
                continue;
            }
            const auto filename = "sam-" + target + "-" + role + ".arrow";
            const auto& pair = report["pairs"][target];
            require(item["name"].asString() == name && item["artifact"].asString() == filename && seen.insert(name).second,
                    "invalid or duplicate source artifact");
            require(item["start_sample"].isInt64() && item["sample_count"].isInt64() &&
                    item["start_sample"].asInt64() == start && item["sample_count"].asInt64() == count &&
                    item["channels"].asInt() == 1 && item["bands"].asInt() == bundle.bands &&
                    item["channel_reduction"].asString() == "mono_no_gain_normalization" &&
                    item["prompt"] == pair["description"] && item["wave_sha256"] == pair[role]["sha256"],
                    "separation stream provenance mismatch");
            const auto& wave = pair[role];
            require(!pair["description"].asString().empty() && wave["artifact"].asString() == target + "-" + role + ".wav" &&
                    std::regex_match(wave["sha256"].asString(), hash_pattern) &&
                    wave["sample_count"].isInt64() && wave["sample_count"].asInt64() == count &&
                    wave["raw_sample_count"].isInt64() && wave["raw_sample_count"].asInt64() >= count &&
                    wave["raw_sample_count"].asInt64() - count < report["codec_hop_samples"].asInt() &&
                    wave["right_trim_samples"].asInt64() == wave["raw_sample_count"].asInt64() - count,
                    "invalid separation waveform provenance");
            const auto source_artifact = manifest_path.parent_path() / filename;
            require(sha256_file(source_artifact) == item["sha256"].asString(), "feature checksum mismatch");
            auto features = read_features(source_artifact, item, start, count, bundle.hop, 2);
            features.target = target;
            features.role = role;
            bundle.sources.push_back(std::move(features));
        }
    }
    return bundle;
}

bool PresenceStream::covers(double seconds) const {
    const double frame = seconds * sample_rate;
    return frame >= start_sample && frame < start_sample + sample_count;
}

float PresenceStream::at(double seconds) const {
    const auto offset = static_cast<std::int64_t>(std::floor(seconds * sample_rate)) - start_sample;
    const auto index = std::clamp<std::int64_t>(offset / frame_samples, 0, static_cast<std::int64_t>(probability.size()) - 1);
    return probability[static_cast<std::size_t>(index)];
}

const PresenceStream* Bundle::presence_for(const std::string& target) const {
    for (const auto& stream : presence)
        if (stream.target == target) return &stream;
    return nullptr;
}

bool FeatureStream::covers(double seconds) const {
    const double frame = seconds * sample_rate;
    return frame >= start_sample && frame < start_sample + sample_count;
}

float FeatureStream::interpolate(const std::vector<float>& values, double seconds) const {
    const double frame = std::clamp((seconds * sample_rate - start_sample) / hop, 0.0, static_cast<double>(values.size() - 1));
    const auto a = static_cast<std::size_t>(frame), b = std::min(a + 1, values.size() - 1);
    return std::lerp(values[a], values[b], static_cast<float>(frame - a));
}

std::vector<float> FeatureStream::spectrum_at(double seconds) const {
    const double frame = std::clamp((seconds * sample_rate - start_sample) / hop, 0.0, static_cast<double>(rms.size() - 1));
    const auto a = static_cast<std::size_t>(frame), b = std::min(a + 1, rms.size() - 1);
    std::vector<float> result(bands);
    for (int i = 0; i < bands; ++i)
        result[i] = std::lerp(spectrum[a * bands + i], spectrum[b * bands + i], static_cast<float>(frame - a));
    return result;
}
} // namespace harmonic
