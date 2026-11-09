# Hypcade modification notice (2026-11-08): Android arcade adaptation.
# See MODIFICATIONS.md; original notices are retained.
cmake_minimum_required(VERSION 3.16)
cmake_policy(SET CMP0074 NEW)

set(PKG_VERSION "v3.0.2")

project(hypseus)

option(BENCHMARK        "Benchmark"             OFF)
option(DEBUG            "Debug"                 OFF)
option(VLDP_DEBUG       "VLDP Debug"            OFF)
option(CPU_DEBUG        "CPU Debug"             OFF)
option(BUILD_SINGE      "Singe"                 ON)
option(BUILDBOT         "Buildbot"              OFF)
option(ASAN             "Address Sanitizer"     OFF)

# Abstract out -espath ES extension: Use .hypseus NOT .daphne
option(ABSTRACT_SINGE   "Redefine Singe LUA Rewrites"     ON)

if (NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE "Release")
endif()

if (UNIX)
  if (CMAKE_SIZEOF_VOID_P EQUAL 4)
      message(STATUS "Compiling with 64-bit file/time support")
      add_compile_definitions(
          _FILE_OFFSET_BITS=64
          _TIME_BITS=64
      )
  endif()
endif()

set(DOWNLOAD_ARGS)
if (CMAKE_VERSION VERSION_GREATER_EQUAL "3.24.0")
    list(APPEND DOWNLOAD_ARGS DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
endif()

add_compile_options(-Wall)
add_compile_definitions(SDL_DISABLE_OLD_NAMES)

if (ASAN)
    add_compile_options(-fsanitize=address -fno-omit-frame-pointer -g)
endif()

list(PREPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake/modules")

include(TargetArch)
target_architecture(CMAKE_TARGET_ARCHITECTURES)

# Config.h defines
string(TOUPPER ${CMAKE_SYSTEM_NAME} TARGET_SYSTEM)
string(CONCAT TARGET_SYSTEM TARGET_ ${TARGET_SYSTEM})
string(TOUPPER ${CMAKE_TARGET_ARCHITECTURES} TARGET_ARCH)
string(CONCAT TARGET_ARCH TARGET_ ${TARGET_ARCH})

include(GNUInstallDirs)
include(GetGitRevisionDescription)
include(InstallRequiredSystemLibraries)
include(FindPkgConfig)
include(ExternalProject)
if(NOT ANDROID)
    include(BuildLibMPEG2)
endif()

set (CMAKE_CXX_STANDARD 11)

if(NOT ANDROID)
    build_libmpeg2( )
elseif(NOT TARGET libmpeg2)
    message(FATAL_ERROR "Use android/app/jni/CMakeLists.txt for an Android build")
endif()

message(STATUS "Target: ${CMAKE_SYSTEM_NAME} ${CMAKE_TARGET_ARCHITECTURES}")

if(ANDROID)
    # Android source distributions need not contain a .git directory. Keep the
    # native version deterministic and independent of third-party git tags.
    set(VER_TAG ${PKG_VERSION})
    set(VER_GIT_COUNT "0")
else()
git_describe(VER_TAG --tags --abbrev=0)
if("${VER_TAG}" MATCHES "-NOTFOUND")
    set(VER_TAG  ${PKG_VERSION})
    set(VER_GIT_COUNT "0")
else()
    git_revlist(VER_GIT_COUNT --count ${VER_TAG}..HEAD)
endif()
endif()
string(REGEX REPLACE "^v" "" RESULT ${VER_TAG})
string(REGEX REPLACE "[-\\.]" ";" RESULT ${RESULT})
list(GET RESULT 0 VER_MAJOR)
list(GET RESULT 1 VER_MINOR)
list(GET RESULT 2 VER_PATCH)
if(NOT "${VER_GIT_COUNT}" EQUAL "0")
    set(VER_TAG "${VER_TAG}-${VER_GIT_COUNT}")
endif()
if(NOT ANDROID)
git_describe(VER_GIT_DIRTY --always --dirty)
if("${VER_GIT_DIRTY}" MATCHES "-dirty")
    set(VER_TAG "${VER_TAG}-dirty")
endif()
endif()
message(STATUS "Version: ${VER_TAG}")

include_directories(
    ${PROJECT_BINARY_DIR} # config.h
)

if( "${CMAKE_TARGET_ARCHITECTURES}" MATCHES "i386" )
    enable_language( ASM )
    set(can_use_assembler TRUE)
endif()

configure_file(
    "${PROJECT_SOURCE_DIR}/config.h.in"
    "${PROJECT_BINARY_DIR}/config.h"
)

if(NOT TARGET SDL3::SDL3)
    find_package(SDL3 CONFIG REQUIRED)
endif()

if( TARGET SDL3::SDL3-shared AND NOT TARGET SDL3::SDL3 )
    add_library( SDL3::SDL3 ALIAS SDL3::SDL3-shared )
endif()

if(NOT TARGET SDL3_ttf::SDL3_ttf)
    find_package(SDL3_ttf CONFIG REQUIRED)
endif()
if(NOT TARGET SDL3_image::SDL3_image)
    find_package(SDL3_image CONFIG REQUIRED)
endif()
if(NOT TARGET SDL3_mixer::SDL3_mixer)
    find_package(SDL3_mixer CONFIG REQUIRED)
endif()
if(NOT TARGET Vorbis::vorbis)
    find_package(Vorbis REQUIRED)
endif()

message(STATUS "SDL3 version: ${SDL3_VERSION}")
message(STATUS "SDL3_ttf version: ${SDL3_ttf_VERSION}")
message(STATUS "SDL3_image version: ${SDL3_image_VERSION}")
message(STATUS "SDL3_mixer version: ${SDL3_mixer_VERSION}")
message(STATUS "Vorbis version: ${Vorbis_VERSION}")

add_library(sdl3_deps INTERFACE)
target_link_libraries(sdl3_deps INTERFACE
    SDL3::SDL3
    SDL3::Headers
    SDL3_ttf::SDL3_ttf
    SDL3_image::SDL3_image
    SDL3_mixer::SDL3_mixer
)

add_subdirectory(3rdparty)

add_subdirectory(cpu)
add_subdirectory(game)
add_subdirectory(manymouse)
add_subdirectory(io)
add_subdirectory(ldp-in)
add_subdirectory(ldp-out)
add_subdirectory(scoreboard)
add_subdirectory(sound)
add_subdirectory(timer)
add_subdirectory(video)
add_subdirectory(vldp)

add_dependencies( vldp libmpeg2 )
add_dependencies( ldp-out vldp )
add_dependencies( game vldp )
add_dependencies( sound vldp )

if(ANDROID)
    add_library(hypseus SHARED hypseus.cpp globals.h
        "${CMAKE_CURRENT_SOURCE_DIR}/../android/app/jni/android_bridge.cpp"
        "${CMAKE_CURRENT_SOURCE_DIR}/../android/app/jni/android_clock.cpp"
        "${CMAKE_CURRENT_SOURCE_DIR}/../android/app/jni/arcade_guidance.cpp"
        "${CMAKE_CURRENT_SOURCE_DIR}/../android/app/jni/android_video_codec.cpp"
        "${CMAKE_CURRENT_SOURCE_DIR}/../android/app/jni/mpeg2_packets.cpp")
    target_include_directories(hypseus PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../android/app/jni")
    # SDLActivity loads libmain.so and resolves its exported SDL_main symbol.
    set_target_properties(hypseus PROPERTIES OUTPUT_NAME main)
else()
    add_executable( hypseus hypseus.cpp globals.h )
endif()
target_link_libraries( hypseus plog io timer sound video cpu game ${Vorbis_Enc_LIBRARY} Vorbis::vorbis ${OGG_LIBRARIES} ${VORBISFILE_LIBRARIES} ${Vorbis_File_LIBRARY} SDL3::SDL3 SDL3::Headers SDL3_ttf::SDL3_ttf SDL3_image::SDL3_image SDL3_mixer::SDL3_mixer ${LIBZIP_LIBRARY} )

if(ANDROID)
    target_link_libraries(hypseus log android)
    target_link_options(hypseus PRIVATE "-Wl,--no-undefined")
endif()

if(ASAN)
    target_link_options(hypseus PRIVATE -fsanitize=address -fno-omit-frame-pointer -g)
endif()

#[[
set_source_files_properties( testvldp.cpp PROPERTIES COMPILE_FLAGS -DSHOW_FRAMES)
add_executable( testvldp testvldp.cpp )
target_link_libraries( testvldp PRIVATE video vldp sdl3_deps )
]]

if(BUILDBOT)
    add_custom_command( TARGET hypseus
        POST_BUILD
	COMMAND ${CMAKE_STRIP} $<TARGET_FILE:hypseus>
        COMMAND ${CMAKE_COMMAND} -E remove -f hypseus.zip
        COMMAND 7za a -mpass=4 -mfb=255 -y -tzip hypseus.zip $<TARGET_FILE:hypseus>
        COMMAND ${CMAKE_COMMAND} -E md5sum hypseus.zip > hypseus.md5
        COMMENT "Create zip and md5 for buildbot")
endif()

set(CPACK_PACKAGE_NAME "Hypseus Singe")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "Hypseus Singe - Arcade Laserdisc Emulator")
set(CPACK_PACKAGE_VENDOR "DirtBagXon")
set(CPACK_PACKAGE_CONTACT "hypseus@users.noreply.github.com")
set(CPACK_PACKAGE_VERSION "${VER_TAG}")
set(CPACK_PACKAGE_VERSION_MAJOR "${VER_MAJOR}")
set(CPACK_PACKAGE_VERSION_MINOR "${VER_MINOR}")
set(CPACK_PACKAGE_VERSION_PATCH "${VER_PATCH}")

include(CPack)
