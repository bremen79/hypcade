# Hypcade modification (2026-11-09): Android hardware decoding recovery.
set( LIB_SOURCES
    vldp.cpp
    vldp_nonstd.cpp
    vldp_internal.cpp
    mpegscan.cpp
)

set( LIB_HEADERS
    mpegscan.h
    vldp_nonstd.h
    vldp_common.h
    vldp.h
    vldp_internal.h
)

if( VLDP_DEBUG )
	set_source_files_properties( ${LIB_SOURCES} PROPERTIES COMPILE_FLAGS -DVLDP_DEBUG )
endif( VLDP_DEBUG )

include_directories( ${MPEG2_INCLUDE_DIRS} )

add_library( vldp ${LIB_SOURCES} ${LIB_HEADERS} )
target_link_libraries( vldp PRIVATE plog ${MPEG2_LIBRARIES} sdl3_deps )

if(ANDROID)
    target_sources(vldp PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../android/app/jni/mpeg2_replay.cpp")
    target_include_directories(vldp PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../android/app/jni")
endif()
