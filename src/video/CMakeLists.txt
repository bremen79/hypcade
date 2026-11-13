# Hypcade: compile the Android video backend only for Android.
set( LIB_SOURCES
    video.cpp
    tms9128nl.cpp
    led.cpp
    palette.cpp
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
    target_sources(video PRIVATE video_android.cpp video_android.h
        "${CMAKE_CURRENT_SOURCE_DIR}/../../android/app/jni/android_crt.cpp")
    target_link_libraries(video PRIVATE GLESv2)
else()
    target_sources(video PRIVATE splash.cpp)
endif()
