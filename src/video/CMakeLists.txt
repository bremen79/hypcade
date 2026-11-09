# Hypcade modification (2026-11-09): build the Android GLES2 CRT adapter.
set( LIB_SOURCES
    video.cpp
    tms9128nl.cpp
    led.cpp
    palette.cpp
    splash.cpp
)

set( LIB_HEADERS
    led.h
    palette.h
    tms9128nl.h
    video.h
    splash.h
    icon.h
)

add_library( video ${LIB_SOURCES} ${LIB_HEADERS} )
target_link_libraries( video PRIVATE plog sdl3_deps )

if(ANDROID)
    target_sources(video PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../android/app/jni/android_crt.cpp")
    target_link_libraries(video PRIVATE GLESv2)
endif()
