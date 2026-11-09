// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef HYPSEUS_ANDROID_CLOCK_H
#define HYPSEUS_ANDROID_CLOCK_H

#include <SDL3/SDL_stdinc.h>

#ifdef __cplusplus
extern "C" {
#endif

// Application time in SDL millisecond units, excluding Android suspension.
// Safe to read from the emulator, video decoder and audio threads.
Uint64 hypseus_android_ticks(void);

// Call once on the SDL thread after SDL_Init(), before starting the emulator.
// A second call during the same SDL lifetime is harmless. Returns false if
// SDL could not register the lifecycle watcher.
bool hypseus_android_clock_install(void);

// Call on the SDL thread after workers stop and before SDL_Quit().
void hypseus_android_clock_remove(void);

#ifdef __cplusplus
}
#endif

#endif
