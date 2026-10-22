#pragma once

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <string>
#include <utility>
#include <unistd.h>

namespace harmonic {
class Progress {
public:
    Progress(std::string label, std::size_t total) : label_(std::move(label)), total_(total) {
        const char* force = std::getenv("FORCE_COLOR");
        const char* term = std::getenv("TERM");
        color_ = !std::getenv("NO_COLOR") &&
            ((force && *force && std::string(force) != "0") ||
             (isatty(fileno(stderr)) && (!term || std::string(term) != "dumb")));
        if (!color_) std::cerr << "🔵 " << label_ << '\n';
        update(0, true);
    }
    ~Progress() { if (!finished_) finish(false); }
    void update(std::size_t done, bool force = false) {
        const auto now = Clock::now();
        if (!color_ || (!force && std::chrono::duration<double>(now - refreshed_).count() < 0.1)) return;
        refreshed_ = now;
        constexpr int width = 24;
        const int filled = static_cast<int>(width * std::min(done, total_) / total_);
        std::cerr << "\r\033[2K🔵 " << label_ << ' ';
        constexpr int stops[3][3] = {{56,189,248}, {167,139,250}, {52,211,153}};
        for (int i = 0; i < width; ++i) {
            if (i < filled) {
                const double position = i * 2.0 / (width - 1);
                const int segment = std::min(1, static_cast<int>(position));
                std::cerr << "\033[38;2";
                for (int channel = 0; channel < 3; ++channel)
                    std::cerr << ';' << static_cast<int>(stops[segment][channel] +
                        (stops[segment + 1][channel] - stops[segment][channel]) * (position - segment));
                std::cerr << "m━";
            } else std::cerr << "\033[90m─";
        }
        std::cerr << "\033[0m " << done << '/' << total_ << "  " << std::fixed << std::setprecision(1)
                  << 100.0 * done / total_ << "%  " << elapsed() << "s" << std::flush;
    }
    void finish(bool success = true) {
        if (finished_) return;
        finished_ = true;
        if (color_) {
            if (success) { update(total_, true); std::cerr << '\n'; }
            else std::cerr << "\r\033[2K";
            std::cerr << (success ? "\033[32m" : "\033[31m");
        }
        std::cerr << (success ? "🟢 " : "🔴 ") << label_ << (success ? ": complete (" : ": failed (")
                  << std::fixed << std::setprecision(1) << elapsed() << "s)";
        if (color_) std::cerr << "\033[0m";
        std::cerr << '\n';
    }
private:
    using Clock = std::chrono::steady_clock;
    double elapsed() const { return std::chrono::duration<double>(Clock::now() - started_).count(); }
    std::string label_;
    std::size_t total_;
    bool color_ = false, finished_ = false;
    Clock::time_point started_ = Clock::now(), refreshed_{};
};
} // namespace harmonic
