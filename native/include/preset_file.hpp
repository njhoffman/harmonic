#pragma once

#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>

namespace harmonic {
inline void validate_preset_file(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("Cannot read preset: " + path.string());
    for (std::string line; std::getline(input, line);) {
        const auto first = line.find_first_not_of(" \t\r");
        if (first != std::string::npos &&
            line.substr(first, line.find_last_not_of(" \t\r") - first + 1) == "[preset00]") return;
    }
    throw std::runtime_error("Preset loading failed: missing [preset00] section");
}
} // namespace harmonic
