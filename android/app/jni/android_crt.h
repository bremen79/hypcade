/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <SDL3/SDL.h>

// Rendering thread only. False means the caller must draw the unfiltered video.
bool android_crt_draw(SDL_Renderer *renderer, SDL_Texture *yuv,
                      const SDL_FRect *source, const SDL_FRect &destination);
// Call before destroying the renderer and its GL context.
void android_crt_reset(SDL_Renderer *renderer);
