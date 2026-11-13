# Hypcade: Copyright (C) 2026 Francesco Orabona.
# Hypcade modification notice (2026-11-08): Android arcade adaptation.
# See android/MODIFICATIONS.md; original notices are retained.
set( LIB_SOURCES
    ldp.cpp
    framemod.cpp
    ldp-vldp.cpp
    ldp-sync.cpp
    ldp-vldp-audio.cpp
)


set( LIB_HEADERS
    framemod.h
    ldp.h
    ldp-vldp.h
    ldp-sync.h
)

if(NOT ANDROID)
IF(NOT APPLE)
    PKG_SEARCH_MODULE(VORBISFILE REQUIRED vorbisfile)
ENDIF(NOT APPLE)

find_package(Vorbis REQUIRED)
find_package(Ogg REQUIRED)

include_directories( ${Vorbis_File_INCLUDE_DIR} ${OGG_INCLUDE_DIRS})
endif()

add_library( ldp-out ${LIB_SOURCES} ${LIB_HEADERS} )
target_link_libraries( ldp-out PRIVATE vldp game plog ${VORBISFILE_LIBRARIES} sdl3_deps )
if(ANDROID)
    target_link_libraries(ldp-out PRIVATE Vorbis::vorbisfile Ogg::ogg)
endif()
