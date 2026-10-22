cmake_minimum_required(VERSION 3.24)
project(harmonic VERSION 0.5.0 LANGUAGES C CXX)

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
    native/src/transport.cpp native/src/renderer.cpp native/src/preset_renderer.cpp
    native/src/compositor_check.cpp)
target_include_directories(harmonic-player PRIVATE native/include)
target_compile_definitions(harmonic-player PRIVATE GL_GLEXT_PROTOTYPES HARMONIC_VERSION="${PROJECT_VERSION}")
target_compile_options(harmonic-player PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(harmonic-player PRIVATE SDL3::SDL3 OpenGL::GL
    PkgConfig::FFMPEG PkgConfig::JSONCPP ${HARMONIC_ARROW_TARGET})

option(HARMONIC_PROJECTM "Enable optional projectM playback when supported by the installed library" ON)
option(HARMONIC_PROJECTM_CHECK "Build the optional libprojectM preset checker when installed" ON)
if(HARMONIC_PROJECTM OR HARMONIC_PROJECTM_CHECK)
    find_package(projectM4 4 QUIET CONFIG)
    if(projectM4_FOUND)
        include(CheckCXXSymbolExists)
        set(CMAKE_REQUIRED_LIBRARIES libprojectM::projectM)
        check_cxx_symbol_exists(projectm_set_frame_time "projectM-4/parameters.h"
            HARMONIC_PROJECTM_FRAME_TIME)
        check_cxx_symbol_exists(projectm_opengl_render_frame_fbo "projectM-4/render_opengl.h"
            HARMONIC_PROJECTM_FRAMEBUFFER)
        unset(CMAKE_REQUIRED_LIBRARIES)
        if(HARMONIC_PROJECTM AND HARMONIC_PROJECTM_FRAME_TIME AND HARMONIC_PROJECTM_FRAMEBUFFER)
            target_compile_definitions(harmonic-player PRIVATE HARMONIC_PROJECTM_PLAYBACK)
            target_link_libraries(harmonic-player PRIVATE libprojectM::projectM)
        endif()
        if(HARMONIC_PROJECTM_CHECK)
            add_executable(harmonic-projectm-check native/src/projectm_check.cpp
                native/src/audio.cpp native/src/bundle.cpp native/src/renderer.cpp)
            target_include_directories(harmonic-projectm-check PRIVATE native/include)
            target_compile_definitions(harmonic-projectm-check PRIVATE GL_GLEXT_PROTOTYPES
                HARMONIC_VERSION="${PROJECT_VERSION}")
            if(HARMONIC_PROJECTM_FRAME_TIME)
                target_compile_definitions(harmonic-projectm-check PRIVATE HARMONIC_PROJECTM_FRAME_TIME)
            endif()
            target_compile_options(harmonic-projectm-check PRIVATE -Wall -Wextra -Wpedantic)
            target_link_libraries(harmonic-projectm-check PRIVATE SDL3::SDL3 OpenGL::GL
                libprojectM::projectM PkgConfig::FFMPEG PkgConfig::JSONCPP ${HARMONIC_ARROW_TARGET})
        endif()
    else()
        message(STATUS "libprojectM 4 not found; building the player without optional preset support")
    endif()
endif()
