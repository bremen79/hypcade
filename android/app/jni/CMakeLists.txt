cmake_minimum_required(VERSION 3.22.1)
project(hypseus_android LANGUAGES C CXX)

if(NOT ANDROID)
    message(FATAL_ERROR "Configure this project with the Android NDK toolchain")
endif()
if(DEFINED ANDROID_PLATFORM_LEVEL)
    set(HYPSEUS_ANDROID_API ${ANDROID_PLATFORM_LEVEL})
else()
    set(HYPSEUS_ANDROID_API ${CMAKE_SYSTEM_VERSION})
endif()
# Android 7.1 (API 25) adds no native APIs; the NDK maps it to API 24.
# The application's minimum remains API 25 in Gradle.
if(HYPSEUS_ANDROID_API LESS 24)
    message(FATAL_ERROR "The Android port requires native API 24 or newer (application minimum: Android 7.1/API 25)")
endif()

get_filename_component(HYPSEUS_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
set(HYPSEUS_DEPS "${HYPSEUS_ROOT}/android/third_party")
foreach(dependency SDL SDL_image SDL_ttf SDL_mixer libzip)
    if(NOT EXISTS "${HYPSEUS_DEPS}/${dependency}/CMakeLists.txt")
        message(FATAL_ERROR "Missing ${dependency}. Run python3 android/bootstrap-deps.py from the repository root first.")
    endif()
endforeach()

# Every archive ultimately becomes part of libmain.so, so it must use PIC.
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "Static dependency libraries" FORCE)
set(CMAKE_C_STANDARD 99)
set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(BUILD_TESTING OFF CACHE BOOL "Do not build dependency tests" FORCE)
# Optimize across static-library boundaries without changing emulated timing
# or enabling unsafe floating-point transformations. CMake 3.22's IPO helper
# selects obsolete gold on Android; use the pinned Clang/LLD ThinLTO directly.
add_compile_options("$<$<CONFIG:Release>:-flto=thin>")
add_link_options("$<$<CONFIG:Release>:-flto=thin>" "-Wl,--thinlto-jobs=2")
add_compile_definitions(_FILE_OFFSET_BITS=64)

# SDLActivity's Java sources and the shared native library are from the same
# pinned checkout. Java is compiled by Gradle, not by SDL's optional jar target.
set(SDL_SHARED ON CACHE BOOL "Build SDL shared" FORCE)
set(SDL_STATIC OFF CACHE BOOL "Do not build a duplicate SDL archive" FORCE)
set(SDL_INSTALL OFF CACHE BOOL "No native install step" FORCE)
set(SDL_ANDROID_JAR OFF CACHE BOOL "Gradle compiles SDL Java" FORCE)
set(SDL_TEST_LIBRARY OFF CACHE BOOL "No SDL test library" FORCE)
set(SDL_TESTS OFF CACHE BOOL "No SDL tests" FORCE)
set(SDL_EXAMPLES OFF CACHE BOOL "No SDL examples" FORCE)
# The engine uses SDL's 2D GLES renderer, never SDL_GPU or a camera. GLES
# retains YUV shader conversion and works on both older and newer Android.
set(SDL_GPU OFF CACHE BOOL "No unused 3D GPU API" FORCE)
set(SDL_RENDER_GPU OFF CACHE BOOL "" FORCE)
set(SDL_VULKAN OFF CACHE BOOL "Use GLES on Android" FORCE)
set(SDL_RENDER_VULKAN OFF CACHE BOOL "" FORCE)
set(SDL_CAMERA OFF CACHE BOOL "No camera capture" FORCE)
add_subdirectory("${HYPSEUS_DEPS}/SDL" SDL EXCLUDE_FROM_ALL)

# Built-in JPEG/PNG and common bitmap loaders cover emulator artwork and Singe
# sprites without adding the much larger AVIF/TIFF/WebP dependency trees.
set(SDLIMAGE_INSTALL OFF CACHE BOOL "" FORCE)
set(SDLIMAGE_VENDORED OFF CACHE BOOL "" FORCE)
set(SDLIMAGE_DEPS_SHARED OFF CACHE BOOL "" FORCE)
set(SDLIMAGE_BACKEND_STB ON CACHE BOOL "" FORCE)
set(SDLIMAGE_PNG_LIBPNG OFF CACHE BOOL "" FORCE)
foreach(format AVIF JXL TIF WEBP)
    set(SDLIMAGE_${format} OFF CACHE BOOL "" FORCE)
endforeach()
set(SDLIMAGE_SAMPLES OFF CACHE BOOL "" FORCE)
set(SDLIMAGE_TESTS OFF CACHE BOOL "" FORCE)
add_subdirectory("${HYPSEUS_DEPS}/SDL_image" SDL_image EXCLUDE_FROM_ALL)

set(SDLTTF_INSTALL OFF CACHE BOOL "" FORCE)
set(SDLTTF_VENDORED ON CACHE BOOL "" FORCE)
set(SDLTTF_HARFBUZZ OFF CACHE BOOL "" FORCE)
set(SDLTTF_PLUTOSVG OFF CACHE BOOL "" FORCE)
set(SDLTTF_SAMPLES OFF CACHE BOOL "" FORCE)
add_subdirectory("${HYPSEUS_DEPS}/SDL_ttf" SDL_ttf EXCLUDE_FROM_ALL)

# libvorbisfile is also used directly by the laserdisc soundtrack reader.
# Keep built-in WAV/AIFF/AU/VOC, dr_mp3 and dr_flac; MIDI was unsupported.
set(SDLMIXER_INSTALL OFF CACHE BOOL "" FORCE)
set(SDLMIXER_VENDORED ON CACHE BOOL "" FORCE)
set(SDLMIXER_DEPS_SHARED OFF CACHE BOOL "" FORCE)
set(SDLMIXER_VORBIS_VORBISFILE ON CACHE BOOL "" FORCE)
set(SDLMIXER_VORBIS_VORBISFILE_SHARED OFF CACHE BOOL "" FORCE)
set(SDLMIXER_VORBIS_STB OFF CACHE BOOL "" FORCE)
set(SDLMIXER_VORBIS_TREMOR OFF CACHE BOOL "" FORCE)
set(SDLMIXER_FLAC_LIBFLAC OFF CACHE BOOL "" FORCE)
set(SDLMIXER_MP3_MPG123 OFF CACHE BOOL "" FORCE)
set(SDLMIXER_MIDI_FLUIDSYNTH OFF CACHE BOOL "" FORCE)
set(SDLMIXER_MIDI OFF CACHE BOOL "No unsupported MIDI synthesis" FORCE)
foreach(codec GME MOD OPUS WAVPACK)
    set(SDLMIXER_${codec} OFF CACHE BOOL "" FORCE)
endforeach()
set(SDLMIXER_TESTS OFF CACHE BOOL "" FORCE)
set(SDLMIXER_EXAMPLES OFF CACHE BOOL "" FORCE)
add_subdirectory("${HYPSEUS_DEPS}/SDL_mixer" SDL_mixer EXCLUDE_FROM_ALL)

if(NOT TARGET Vorbis::vorbis)
    add_library(Vorbis::vorbis ALIAS vorbis)
endif()
if(NOT TARGET Vorbis::vorbisenc)
    add_library(Vorbis::vorbisenc ALIAS vorbisenc)
endif()
set(Vorbis_Enc_LIBRARY Vorbis::vorbisenc)
set(Vorbis_File_LIBRARY Vorbis::vorbisfile)
set(VORBISFILE_LIBRARIES Vorbis::vorbisfile)
set(OGG_LIBRARIES Ogg::ogg)

# The Android platform supplies zlib. ZIP's optional encryption and uncommon
# compression backends are not required for ordinary ROM/Singe packages.
foreach(option ENABLE_COMMONCRYPTO ENABLE_GNUTLS ENABLE_MBEDTLS ENABLE_OPENSSL
        ENABLE_WINDOWS_CRYPTO ENABLE_BZIP2 ENABLE_LZMA ENABLE_ZSTD BUILD_TOOLS
        BUILD_REGRESS BUILD_OSSFUZZ BUILD_EXAMPLES BUILD_DOC LIBZIP_DO_INSTALL)
    set(${option} OFF CACHE BOOL "" FORCE)
endforeach()
add_subdirectory("${HYPSEUS_DEPS}/libzip" libzip EXCLUDE_FROM_ALL)
set(LIBZIP_LIBRARY libzip::zip)

# Use the exact MPEG-2 decoder archive shipped by upstream. Building its
# portable C backend directly avoids running host autotools during cross-builds
# and avoids obsolete architecture-specific assembly on Android's ABIs.
set(mpeg2_archive "${HYPSEUS_ROOT}/src/3rdparty/libmpeg2/libmpeg2-master.tgz")
file(SHA256 "${mpeg2_archive}" mpeg2_sha256)
if(NOT mpeg2_sha256 STREQUAL "5cbf94a93995b485ffe0040bf3221264c2dfe836d316d24c33b58fe808d985b5")
    message(FATAL_ERROR "Unexpected bundled libmpeg2 archive checksum")
endif()
set(mpeg2_source "${CMAKE_CURRENT_BINARY_DIR}/mpeg2-src/libmpeg2-master")
if(NOT EXISTS "${mpeg2_source}/libmpeg2/decode.c")
    file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/mpeg2-src")
    file(ARCHIVE_EXTRACT INPUT "${mpeg2_archive}" DESTINATION "${CMAKE_CURRENT_BINARY_DIR}/mpeg2-src")
endif()
set(mpeg2_config "${CMAKE_CURRENT_BINARY_DIR}/mpeg2-config")
file(MAKE_DIRECTORY "${mpeg2_config}")
file(WRITE "${mpeg2_config}/config.h" "\
#define HAVE_INTTYPES_H 1\n\
#define HAVE_STDINT_H 1\n\
#define HAVE_STDLIB_H 1\n\
#define HAVE_STRING_H 1\n\
#define HAVE_MEMORY_H 1\n\
#define HAVE_SYS_TYPES_H 1\n\
#define HAVE_BUILTIN_EXPECT 1\n\
#define ATTRIBUTE_ALIGNED_MAX 64\n\
#define restrict __restrict\n")
set(mpeg2_files alloc.c header.c decode.c slice.c motion_comp.c idct.c cpu_accel.c cpu_state.c)
list(TRANSFORM mpeg2_files PREPEND "${mpeg2_source}/libmpeg2/")
add_library(libmpeg2 STATIC ${mpeg2_files})
target_include_directories(libmpeg2 PRIVATE "${mpeg2_config}" PUBLIC "${mpeg2_source}/include")
set_target_properties(libmpeg2 PROPERTIES C_STANDARD 90 C_EXTENSIONS ON)
target_compile_options(libmpeg2 PRIVATE -Wno-deprecated-non-prototype)
# Preserve the pinned archive; accelerate motion compensation and IDCT on ARM.
if(ANDROID_ABI MATCHES "^(arm64-v8a|armeabi-v7a)$")
    set_source_files_properties("${mpeg2_source}/libmpeg2/motion_comp.c"
        PROPERTIES COMPILE_DEFINITIONS "mpeg2_mc_init=mpeg2_mc_init_portable")
    set_source_files_properties("${mpeg2_source}/libmpeg2/idct.c"
        PROPERTIES COMPILE_DEFINITIONS "mpeg2_idct_init=mpeg2_idct_init_portable")
    target_sources(libmpeg2 PRIVATE mpeg2_motion_dispatch.c mpeg2_motion_neon.c mpeg2_idct_neon.c)
    target_include_directories(libmpeg2 PRIVATE "${mpeg2_source}/libmpeg2")
    if(ANDROID_ABI STREQUAL "armeabi-v7a")
        set_source_files_properties(mpeg2_motion_neon.c mpeg2_idct_neon.c PROPERTIES COMPILE_OPTIONS "-mfpu=neon")
    endif()
endif()

set(MPEG2_INCLUDE_DIRS "${mpeg2_source}/include")
set(MPEG2_LIBRARIES libmpeg2)

set(BUILD_SINGE ON CACHE BOOL "Build the Singe scripting engine" FORCE)
set(BUILDBOT OFF CACHE BOOL "Do not run desktop packaging" FORCE)
add_subdirectory("${HYPSEUS_ROOT}/src" hypseus)
