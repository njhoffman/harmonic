cmake_minimum_required(VERSION 3.24)
project(harmonic VERSION 0.3.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(PkgConfig REQUIRED)
pkg_check_modules(FFMPEG REQUIRED IMPORTED_TARGET libavformat libavcodec libavutil libswresample)
pkg_check_modules(JSONCPP REQUIRED IMPORTED_TARGET jsoncpp)
find_package(OpenGL REQUIRED)
find_package(SDL3 3.2 QUIET CONFIG)
if(NOT SDL3_FOUND)
    include(FetchContent)
    set(SDL_TESTS OFF CACHE BOOL "" FORCE)
    set(SDL_TEST_LIBRARY OFF CACHE BOOL "" FORCE)
    set(SDL_EXAMPLES OFF CACHE BOOL "" FORCE)
    set(SDL_SHARED OFF CACHE BOOL "" FORCE)
    set(SDL_STATIC ON CACHE BOOL "" FORCE)
    FetchContent_Declare(SDL3
        GIT_REPOSITORY https://github.com/libsdl-org/SDL.git
        GIT_TAG release-3.4.18
        GIT_SHALLOW TRUE)
    FetchContent_MakeAvailable(SDL3)
endif()

find_package(Arrow QUIET CONFIG)
if(Arrow_FOUND)
    set(HARMONIC_ARROW_TARGET Arrow::arrow_shared)
else()
    # PyArrow wheels ship the matching C++ headers and shared library. This is a
    # development fallback; a packaged player should use a native Arrow package.
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    execute_process(COMMAND "${Python3_EXECUTABLE}" -c
        "import pyarrow; print(pyarrow.get_include()); print(pyarrow.get_library_dirs()[0])"
        RESULT_VARIABLE ARROW_QUERY_STATUS OUTPUT_VARIABLE ARROW_PATHS
        ERROR_QUIET OUTPUT_STRIP_TRAILING_WHITESPACE)
    if(NOT ARROW_QUERY_STATUS EQUAL 0)
        message(FATAL_ERROR "Install Python dependencies with uv sync and configure with -DPython3_EXECUTABLE=${CMAKE_SOURCE_DIR}/.venv/bin/python, or install Arrow C++.")
    endif()
    string(REPLACE "\n" ";" ARROW_PATHS "${ARROW_PATHS}")
    list(GET ARROW_PATHS 0 ARROW_INCLUDE_DIR)
    list(GET ARROW_PATHS 1 ARROW_LIBRARY_DIR)
    file(GLOB ARROW_LIBRARIES "${ARROW_LIBRARY_DIR}/libarrow.so.*" "${ARROW_LIBRARY_DIR}/libarrow.dylib")
    list(SORT ARROW_LIBRARIES COMPARE NATURAL ORDER DESCENDING)
    list(GET ARROW_LIBRARIES 0 ARROW_LIBRARY)
    add_library(harmonic_arrow SHARED IMPORTED)
    set_target_properties(harmonic_arrow PROPERTIES
        IMPORTED_LOCATION "${ARROW_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${ARROW_INCLUDE_DIR}")
    set(HARMONIC_ARROW_TARGET harmonic_arrow)
endif()

add_executable(harmonic-player
    native/src/main.cpp native/src/audio.cpp native/src/bundle.cpp
    native/src/transport.cpp native/src/renderer.cpp)
target_include_directories(harmonic-player PRIVATE native/include)
target_compile_definitions(harmonic-player PRIVATE GL_GLEXT_PROTOTYPES HARMONIC_VERSION="${PROJECT_VERSION}")
target_compile_options(harmonic-player PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(harmonic-player PRIVATE SDL3::SDL3 OpenGL::GL
    PkgConfig::FFMPEG PkgConfig::JSONCPP ${HARMONIC_ARROW_TARGET})
