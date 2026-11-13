# Hypcade: Copyright (C) 2026 Francesco Orabona.
# Hypcade modification notice (2026-11-08): Android arcade adaptation.
# See MODIFICATIONS.md; original notices are retained.
set( LIB_SOURCES
    sound.cpp
    ssi263.cpp
    tqsynth.cpp
    sn_intf.cpp
    tms9919-sdl.cpp
    tms9919.cpp
    pc_beeper.cpp
    gisound.cpp
    dac.cpp
    tonegen.cpp
    samples.cpp
    mix.cpp
)

# Legacy x86 MMX assembly uses absolute relocations and cannot be loaded in an
# Android shared library. Android uses the existing portable C mixer.
if(NOT ANDROID)
    list(APPEND LIB_SOURCES mix_mmx-gas.s)
endif()

set( LIB_HEADERS
    dac.h
    gisound.h
    mix.h
    pc_beeper.h
    samples.h
    sn_intf.h
    sound.h
    ssi263.h
    tonegen.h
    tqsynth.h
)

add_library( sound ${LIB_SOURCES} ${LIB_HEADERS} )
target_link_libraries( sound PRIVATE plog sdl3_deps )
