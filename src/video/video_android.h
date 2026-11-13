/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <SDL3/SDL.h>
#include <mutex>

namespace video {
void set_show_fps(bool enabled);
void set_android_mobile_display(bool enabled);
namespace android_video {
// Decoder and renderer share this lock. Destroy retired textures only on the
// rendering thread; release it before SDL_RenderPresent/vsync.
std::recursive_mutex &mutex();
void retire_texture(SDL_Texture *texture);
void release_retired_textures();
void release_renderer(SDL_Renderer *renderer);

bool mobile_display();
void drawable_size(SDL_Window *window, SDL_Rect &size);
bool resized(SDL_Window *window, bool fullscreen, SDL_Rect &size);
bool direct_render(SDL_Renderer *renderer, const SDL_Rect &output,
                   const SDL_Rect &picture, bool rotated);
// Returns a cached output-sized CRT target, or null for plain rendering.
SDL_Texture *game_target(SDL_Renderer *renderer, const SDL_Rect &output,
                         bool crt, bool linear);
void present_game(SDL_Renderer *renderer, SDL_Texture *target);

bool init_text(SDL_Renderer *renderer, SDL_Surface *font, bool linear,
               const char *game, bool native_prompts);
// Caller holds mutex(), including while reading the shared text coordinates.
void queue_text(unsigned slot, const char *text, int x, int y);
bool has_rom_text();
void draw_game_text(SDL_Renderer *renderer, const SDL_FRect &canvas,
                    const SDL_FRect &picture);
void draw_hud(SDL_Renderer *renderer, int height, double maximum_fps);
} } // namespace video::android_video
