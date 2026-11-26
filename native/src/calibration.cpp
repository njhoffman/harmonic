#include "harmonic.hpp"

#include <cmath>
#include <cstdlib>
#include <ctime>
#include <fstream>
#include <sstream>
#include <stdexcept>

namespace harmonic {
namespace {
constexpr const char* calibration_kind = "harmonic.calibration.v1";

std::string utc_now() {
    const std::time_t now = std::time(nullptr);
    std::tm utc{};
    gmtime_r(&now, &utc);
    char text[32];
    std::strftime(text, sizeof text, "%Y-%m-%dT%H:%M:%SZ", &utc);
    return text;
}

// Parses the file, or explains why it cannot be used. A missing file is valid
// and empty; any other problem leaves `error` set so callers neither apply nor
// overwrite it.
struct Parsed {
    Json::Value root;
    std::string error;
};

Parsed parse(const std::filesystem::path& path) {
    Parsed parsed;
    parsed.root["kind"] = calibration_kind;
    parsed.root["devices"] = Json::Value(Json::objectValue);
    std::error_code code;
    if (!std::filesystem::exists(path, code)) return parsed;
    std::ifstream input(path);
    Json::CharReaderBuilder reader;
    Json::Value root;
    std::string errors;
    if (!input || !Json::parseFromStream(reader, input, &root, &errors)) {
        parsed.error = "unreadable JSON";
        return parsed;
    }
    if (!root.isObject() || root["kind"] != calibration_kind || !root["devices"].isObject()) {
        parsed.error = std::string("expected kind ") + calibration_kind + " with a devices object";
        return parsed;
    }
    for (const auto& name : root["devices"].getMemberNames()) {
        const auto& entry = root["devices"][name];
        if (!entry.isObject() || !entry["offset_ms"].isNumeric() ||
            !std::isfinite(entry["offset_ms"].asDouble()) ||
            std::abs(entry["offset_ms"].asDouble()) > max_offset_seconds * 1000) {
            parsed.error = "device \"" + name + "\" needs a finite offset_ms within +/-" +
                std::to_string(static_cast<int>(max_offset_seconds * 1000));
            return parsed;
        }
    }
    parsed.root = root;
    return parsed;
}
} // namespace

std::filesystem::path calibration_path() {
    const char* config = std::getenv("XDG_CONFIG_HOME");
    if (config && *config && std::filesystem::path(config).is_absolute())
        return std::filesystem::path(config) / "harmonic" / "calibration.json";
    const char* home = std::getenv("HOME");
    if (!home || !*home) throw std::runtime_error("Cannot locate the calibration file: HOME is not set");
    return std::filesystem::path(home) / ".config" / "harmonic" / "calibration.json";
}

Calibration load_calibration(const std::filesystem::path& path, const std::string& device) {
    Calibration calibration;
    calibration.path = path;
    const auto parsed = parse(path);
    calibration.error = parsed.error;
    if (!parsed.error.empty()) return calibration;
    const auto& entry = parsed.root["devices"][device];
    if (entry.isObject()) calibration.offset_ms = entry["offset_ms"].asDouble();
    return calibration;
}

void save_calibration(const std::filesystem::path& path, const std::string& device, double offset_ms) {
    if (!std::isfinite(offset_ms) || std::abs(offset_ms) > max_offset_seconds * 1000)
        throw std::runtime_error("Calibration offset is out of range");
    auto parsed = parse(path);
    if (!parsed.error.empty())
        throw std::runtime_error("Refusing to overwrite " + path.string() + " (" + parsed.error + "); fix or remove it");
    Json::Value entry;
    // Store whole tenths of a millisecond; the controls step in 10 ms.
    entry["offset_ms"] = std::round(offset_ms * 10) / 10;
    entry["saved"] = utc_now();
    entry["player_version"] = HARMONIC_VERSION;
    parsed.root["devices"][device] = entry;
    std::filesystem::create_directories(path.parent_path());
    const auto temporary = std::filesystem::path(path.string() + ".tmp");
    {
        std::ofstream output(temporary);
        Json::StreamWriterBuilder writer;
        writer["indentation"] = "  ";
        output << Json::writeString(writer, parsed.root) << '\n';
        if (!output) throw std::runtime_error("Cannot write " + temporary.string());
    }
    std::filesystem::rename(temporary, path);
}
} // namespace harmonic
