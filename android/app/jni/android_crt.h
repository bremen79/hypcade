/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <SDL3/SDL.h>

// Rendering thread only. Unsupported renderers never need a CRT framebuffer.
bool android_crt_available(SDL_Renderer *renderer);
// Present an output-sized, composed RGBA32 game layer (video, native text, moves). False means plain copy.
bool android_crt_present(SDL_Renderer *renderer, SDL_Texture *frame);
// Call before destroying the renderer and its GL context.
void android_crt_reset(SDL_Renderer *renderer);
