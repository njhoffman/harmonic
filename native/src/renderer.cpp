#include "harmonic.hpp"

#include <SDL3/SDL_opengl.h>

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <unordered_map>

namespace harmonic {
namespace {
const std::unordered_map<char, std::array<unsigned char, 7>> font = {
    {'A',{14,17,17,31,17,17,17}}, {'B',{30,17,17,30,17,17,30}},
    {'C',{14,17,16,16,16,17,14}}, {'D',{30,17,17,17,17,17,30}},
    {'E',{31,16,16,30,16,16,31}}, {'F',{31,16,16,30,16,16,16}},
    {'G',{14,17,16,23,17,17,15}}, {'H',{17,17,17,31,17,17,17}},
    {'I',{31,4,4,4,4,4,31}}, {'J',{7,2,2,2,18,18,12}},
    {'K',{17,18,20,24,20,18,17}}, {'L',{16,16,16,16,16,16,31}},
    {'M',{17,27,21,21,17,17,17}}, {'N',{17,25,21,19,17,17,17}},
    {'O',{14,17,17,17,17,17,14}}, {'P',{30,17,17,30,16,16,16}},
    {'Q',{14,17,17,17,21,18,13}}, {'R',{30,17,17,30,20,18,17}},
    {'S',{15,16,16,14,1,1,30}}, {'T',{31,4,4,4,4,4,4}},
    {'U',{17,17,17,17,17,17,14}}, {'V',{17,17,17,17,17,10,4}},
    {'W',{17,17,17,21,21,21,10}}, {'X',{17,17,10,4,10,17,17}},
    {'Y',{17,17,10,4,4,4,4}}, {'Z',{31,1,2,4,8,16,31}},
    {'0',{14,17,19,21,25,17,14}}, {'1',{4,12,4,4,4,4,14}},
    {'2',{14,17,1,2,4,8,31}}, {'3',{30,1,1,14,1,1,30}},
    {'4',{2,6,10,18,31,2,2}}, {'5',{31,16,16,30,1,1,30}},
    {'6',{14,16,16,30,17,17,14}}, {'7',{31,1,2,4,8,8,8}},
    {'8',{14,17,17,14,17,17,14}}, {'9',{14,17,17,15,1,1,14}},
    {':',{0,4,4,0,4,4,0}}, {'.',{0,0,0,0,0,12,12}},
    {'-',{0,0,0,31,0,0,0}}, {'/',{1,2,2,4,8,8,16}},
    {'+',{0,4,4,31,4,4,0}}, {'[',{14,8,8,8,8,8,14}},
    {']',{14,2,2,2,2,2,14}}, {'(',{2,4,8,8,8,4,2}},
    {')',{8,4,2,2,2,4,8}}, {'=',{0,31,0,31,0,0,0}},
    {',',{0,0,0,0,0,4,8}}, {'?',{14,17,1,2,4,0,4}},
    {'%',{17,2,4,8,17,0,0}}, {'_',{0,0,0,0,0,0,31}},
};
std::string time_text(double seconds) {
    const int whole = std::max(0, static_cast<int>(seconds));
    std::ostringstream out;
    out << whole / 60 << ':' << std::setfill('0') << std::setw(2) << whole % 60;
    return out.str();
}
std::string number(double value, int precision = 1) {
    std::ostringstream out;
    out << std::fixed << std::setprecision(precision) << value;
    return out.str();
}
GLuint compile(GLenum type, const char* source) {
    const GLuint shader = glCreateShader(type);
    glShaderSource(shader, 1, &source, nullptr);
    glCompileShader(shader);
    GLint good = 0;
    glGetShaderiv(shader, GL_COMPILE_STATUS, &good);
    if (!good) {
        std::array<char, 2048> log{};
        glGetShaderInfoLog(shader, log.size(), nullptr, log.data());
        glDeleteShader(shader);
        throw std::runtime_error(std::string("Shader compilation failed: ") + log.data());
    }
    return shader;
}
} // namespace

Renderer::Renderer(int width, int height, bool hidden) {
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
    window_ = SDL_CreateWindow("Harmonic / Mix inspector", width, height,
        SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY |
        (hidden ? SDL_WINDOW_HIDDEN : 0));
    if (!window_) throw std::runtime_error(std::string("Create window: ") + SDL_GetError());
    SDL_SetWindowMinimumSize(window_, 920, 720);
    context_ = SDL_GL_CreateContext(window_);
    if (!context_) {
        const std::string error = SDL_GetError();
        SDL_DestroyWindow(window_);
        window_ = nullptr;
        throw std::runtime_error("Create OpenGL 3.3 context: " + error);
    }
    SDL_GL_SetSwapInterval(1);
    const char* vertex = R"GLSL(#version 330 core
layout(location=0) in vec2 position;
layout(location=1) in vec4 color;
uniform vec2 resolution;
out vec4 fragment_color;
void main() {
    gl_Position = vec4(position.x / resolution.x * 2.0 - 1.0,
                       1.0 - position.y / resolution.y * 2.0, 0.0, 1.0);
    fragment_color = color;
})GLSL";
    const char* fragment = R"GLSL(#version 330 core
in vec4 fragment_color;
out vec4 output_color;
void main() { output_color = fragment_color; }
)GLSL";
    const auto vs = compile(GL_VERTEX_SHADER, vertex), fs = compile(GL_FRAGMENT_SHADER, fragment);
    program_ = glCreateProgram();
    glAttachShader(program_, vs);
    glAttachShader(program_, fs);
    glLinkProgram(program_);
    glDeleteShader(vs);
    glDeleteShader(fs);
    GLint good = 0;
    glGetProgramiv(program_, GL_LINK_STATUS, &good);
    if (!good) throw std::runtime_error("Could not link the graph shaders");
    resolution_ = glGetUniformLocation(program_, "resolution");
    glGenVertexArrays(1, &vao_);
    glGenBuffers(1, &vbo_);
    glBindVertexArray(vao_);
    glBindBuffer(GL_ARRAY_BUFFER, vbo_);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, sizeof(Vertex), nullptr);
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 4, GL_FLOAT, GL_FALSE, sizeof(Vertex), reinterpret_cast<void*>(2 * sizeof(float)));
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
}

Renderer::~Renderer() {
    if (context_) {
        glDeleteBuffers(1, &vbo_);
        glDeleteVertexArrays(1, &vao_);
        glDeleteProgram(program_);
        SDL_GL_DestroyContext(context_);
    }
    if (window_) SDL_DestroyWindow(window_);
}

void Renderer::rect(float x, float y, float w, float h, float r, float g, float b, float a) {
    vertices_.insert(vertices_.end(), {
        {x,y,r,g,b,a}, {x+w,y,r,g,b,a}, {x,y+h,r,g,b,a},
        {x+w,y,r,g,b,a}, {x+w,y+h,r,g,b,a}, {x,y+h,r,g,b,a},
    });
}

void Renderer::text(float x, float y, const std::string& value, float scale, float r, float g, float b) {
    for (unsigned char character : value) {
        if (character != ' ') {
            const auto found = font.find(static_cast<char>(std::toupper(character)));
            const auto& rows = found == font.end() ? font.at('?') : found->second;
            for (int row = 0; row < 7; ++row)
                for (int col = 0; col < 5; ++col)
                    if (rows[row] & (1 << (4 - col))) rect(x + col * scale, y + row * scale, scale, scale, r, g, b);
        }
        x += scale * 6;
    }
}

void Renderer::draw(const Bundle& bundle, double seconds, bool paused, double offset, bool relative) {
    int width, height, pixels_w, pixels_h;
    SDL_GetWindowSize(window_, &width, &height);
    SDL_GetWindowSizeInPixels(window_, &pixels_w, &pixels_h);
    glViewport(0, 0, pixels_w, pixels_h);
    glClearColor(0.031f, 0.047f, 0.067f, 1);
    glClear(GL_COLOR_BUFFER_BIT);
    vertices_.clear();
    const float left = timeline_left, span = width - 2 * left;
    rect(0, 0, width, 4, 0.22f, 0.86f, 0.72f);
    text(left, 26, "HARMONIC", 3, 0.88f, 0.94f, 0.96f);
    text(left + 186, 34, "/ MIX INSPECTOR", 1.5f, 0.43f, 0.56f, 0.65f);
    std::string title = bundle.audio_path.stem().string();
    const auto max_title = static_cast<std::size_t>((span - 240) / 12);
    if (title.size() > max_title) title = title.substr(0, max_title - 3) + "...";
    text(left, 69, title, 2, 0.85f, 0.9f, 0.94f);
    text(width - 240, 70, time_text(seconds) + " / " + time_text(bundle.duration()), 2, 0.25f, 0.88f, 0.75f);
    const double feature_time = std::clamp(seconds + offset, 0.0, bundle.duration());
    const float rms = bundle.interpolate(bundle.rms, feature_time);
    const float peak = bundle.interpolate(bundle.peak, feature_time);
    const float onset = std::clamp(bundle.interpolate(bundle.onset, feature_time) / bundle.onset_scale, 0.0f, 1.0f);
    text(left, 109, "RMS " + number(20 * std::log10(std::max(1e-6f, rms))) + " DBFS", 1.5f, 0.51f, 0.65f, 0.73f);
    text(left + 210, 109, "PEAK " + number(20 * std::log10(std::max(1e-6f, peak))) + " DBFS", 1.5f, 0.51f, 0.65f, 0.73f);
    text(left + 440, 109, "ONSET", 1.5f, 0.51f, 0.65f, 0.73f);
    rect(left + 502, 108, 95, 12, 0.09f, 0.15f, 0.2f);
    rect(left + 502, 108, 95 * onset, 12, 0.96f, 0.65f, 0.32f);
    text(width - 260, 109, "OFFSET " + number(offset * 1000, 0) + " MS", 1.5f, 0.51f, 0.65f, 0.73f);

    constexpr float top = 154, graph_height = 270;
    rect(left - 14, top - 16, span + 28, graph_height + 57, 0.046f, 0.072f, 0.1f);
    for (int line = 0; line <= 3; ++line) {
        const float y = top + line * graph_height / 3;
        rect(left, y, span, 1, 0.1f, 0.15f, 0.2f);
    }
    const auto spectrum = bundle.spectrum_at(feature_time);
    const float top_db = relative ? bundle.spectrum_top_db : 0;
    const float band_width = span / bundle.bands;
    for (int i = 0; i < bundle.bands; ++i) {
        const float db = 20 * std::log10(std::max(1e-12f, spectrum[i]));
        const float amount = std::clamp((db - (top_db - 70)) / 70, 0.0f, 1.0f);
        const float color = static_cast<float>(i) / bundle.bands;
        const float r = std::lerp(0.18f, 0.95f, color), g = std::lerp(0.82f, 0.64f, color);
        const float b = std::lerp(0.76f, 0.37f, color);
        rect(left + i * band_width + 1, top + graph_height * (1 - amount), std::max(1.0f, band_width - 3), graph_height * amount, r, g, b);
    }
    for (float frequency : {20.0f, 100.0f, 1000.0f, 10000.0f, 24000.0f}) {
        const float fraction = std::log(frequency / 20) / std::log(24000.0f / 20);
        const auto label = frequency >= 1000 ? number(frequency / 1000, 0) + " KHZ" : number(frequency, 0) + " HZ";
        text(std::clamp(left + fraction * span - 15, left, left + span - 72), 438, label, 1.4f, 0.4f, 0.54f, 0.62f);
    }

    text(left, 470, "TRACK ENVELOPE / CLICK TO SEEK", 1.4f, 0.51f, 0.65f, 0.73f);
    constexpr float envelope_top = 494, envelope_height = 105;
    rect(left, envelope_top, span, envelope_height, 0.046f, 0.072f, 0.1f);
    const int columns = static_cast<int>(span);
    const float amplitude_scale = relative ? bundle.rms_scale : 1;
    for (int x = 0; x < columns; ++x) {
        const auto a = static_cast<std::size_t>(x) * bundle.rms.size() / columns;
        const auto b = std::min(bundle.rms.size(), std::max(a + 1, static_cast<std::size_t>(x + 1) * bundle.rms.size() / columns));
        const float value = *std::max_element(bundle.rms.begin() + a, bundle.rms.begin() + b);
        const float h = envelope_height * std::clamp(value / amplitude_scale, 0.0f, 1.0f);
        rect(left + x, envelope_top + envelope_height - h, 1, h, 0.15f, 0.47f, 0.46f);
    }
    const float playhead = left + static_cast<float>(seconds / bundle.duration()) * span;
    rect(playhead, envelope_top - 2, 2, envelope_height + 4, 0.87f, 0.96f, 0.94f);
    const float feature_head = left + static_cast<float>(feature_time / bundle.duration()) * span;
    if (std::abs(offset) >= 0.005) rect(feature_head, envelope_top, 1, envelope_height, 0.97f, 0.65f, 0.32f);

    rect(left, 625, 118, 38, 0.13f, 0.32f, 0.3f);
    text(left + 18, 637, paused ? "PLAY" : "PAUSE", 2, 0.79f, 0.97f, 0.89f);
    rect(left + 132, 625, 126, 38, 0.08f, 0.13f, 0.18f);
    text(left + 145, 637, "RESTART", 2, 0.65f, 0.77f, 0.83f);
    rect(left + 272, 625, 194, 38, 0.08f, 0.13f, 0.18f);
    text(left + 284, 637, relative ? "NORMALIZED" : "ABSOLUTE", 2, 0.65f, 0.77f, 0.83f);
    text(left + 492, 629, "SPACE PLAY/PAUSE   ARROWS SEEK", 1.3f, 0.43f, 0.56f, 0.65f);
    text(left + 492, 648, "N SCALE   ,/. OFFSET   HOME RESTART", 1.3f, 0.43f, 0.56f, 0.65f);
    text(left, 690, "ORIGINAL MIX / 48 KHZ STEREO / 64 LOG BANDS / 50 FRAMES PER SECOND", 1.3f, 0.3f, 0.43f, 0.52f);
    glUseProgram(program_);
    glUniform2f(resolution_, width, height);
    glBindVertexArray(vao_);
    glBindBuffer(GL_ARRAY_BUFFER, vbo_);
    glBufferData(GL_ARRAY_BUFFER, vertices_.size() * sizeof(Vertex), vertices_.data(), GL_STREAM_DRAW);
    glDrawArrays(GL_TRIANGLES, 0, static_cast<GLsizei>(vertices_.size()));
}

void Renderer::screenshot(const std::filesystem::path& path) {
    int width, height;
    SDL_GetWindowSizeInPixels(window_, &width, &height);
    std::vector<unsigned char> pixels(static_cast<std::size_t>(width) * height * 3);
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE, pixels.data());
    std::ofstream out(path, std::ios::binary);
    if (!out) throw std::runtime_error("Cannot write screenshot: " + path.string());
    out << "P6\n" << width << ' ' << height << "\n255\n";
    for (int y = height - 1; y >= 0; --y)
        out.write(reinterpret_cast<const char*>(pixels.data() + static_cast<std::size_t>(y) * width * 3), width * 3);
    if (!out) throw std::runtime_error("Failed writing screenshot");
}
} // namespace harmonic
