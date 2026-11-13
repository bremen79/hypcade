/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* Android video adaptation of Hypseus Singe; original video code copyright
 * (C) 2001 Matt Ownby, 2026 DirtBagXon. Original notices remain in video.cpp. */
// SPDX-License-Identifier: GPL-3.0-or-later
#include "video_android.h"
#include "../../android/app/jni/android_crt.h"
#include "../../android/app/jni/android_ldp1450_text.h"
#include "../../android/app/jni/arcade_guidance.h"
#include <plog/Log.h>
#include <vector>
#include <cstring>
#include <cstdio>

namespace video {
namespace {
bool mobile = false;
SDL_Texture *g_ldp1450_font = nullptr;
bool calculated_moves_enabled = false;
Ldp1450Text g_ldp1450_lines[3];
bool rom_text_active = false;
std::recursive_mutex yuv_mutex;
std::vector<SDL_Texture *> retired_textures;
SDL_Texture *crt_texture = nullptr;
int crt_width = 0, crt_height = 0, failed_width = 0, failed_height = 0;
static bool g_show_fps = false;
static Uint64 g_fps_start = 0;
static unsigned g_fps_frames = 0;
static char g_fps_label[64] = "FPS: --";

}

void set_android_mobile_display(bool enabled) { mobile = enabled; }

void set_show_fps(bool enabled)
{
    g_show_fps = enabled;
    g_fps_start = 0;
    g_fps_frames = 0;
}

namespace android_video {

void draw_hud(SDL_Renderer *renderer, int height, double maximum)
{
    if (!g_show_fps) return;
    const Uint64 now = SDL_GetTicks();
    if (!g_fps_start || now - g_fps_start > 2000) {
        g_fps_start = now;
        g_fps_frames = 0;
    }
    if (now - g_fps_start >= 1000) {
        const double fps = g_fps_frames * 1000.0 / (now - g_fps_start);
        if (maximum > 0.0)
            snprintf(g_fps_label, sizeof(g_fps_label), "FPS: %.1f (max %.1f)", fps, maximum);
        else
            snprintf(g_fps_label, sizeof(g_fps_label), "FPS: %.1f", fps);
        g_fps_frames = 0;
        g_fps_start = now;
    }
    ++g_fps_frames;
    float sx, sy;
    Uint8 r, g, b, a;
    SDL_GetRenderScale(renderer, &sx, &sy);
    SDL_GetRenderDrawColor(renderer, &r, &g, &b, &a);
    const float scale = height >= 1080 ? 3.0f : height >= 600 ? 2.0f : 1.0f;
    SDL_SetRenderScale(renderer, sx * scale, sy * scale);
    const float y = height / scale - SDL_DEBUG_TEXT_FONT_CHARACTER_SIZE;
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    SDL_RenderDebugText(renderer, 5, y + 1, g_fps_label);
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 255);
    SDL_RenderDebugText(renderer, 4, y, g_fps_label);
    SDL_SetRenderDrawColor(renderer, r, g, b, a);
    SDL_SetRenderScale(renderer, sx, sy);
}

static void draw_recorded_move(SDL_Renderer *renderer, const SDL_FRect &picture)
{
    if (!calculated_moves_enabled || !g_ldp1450_font) return;
    const unsigned controls = arcade_visual_controls();
    if (!controls) return;
    static unsigned previous = 0;
    static char text[64] = {};
    if (controls != previous) {
        const char *names[] = {"UP", "DOWN", "LEFT", "RIGHT", "BUTTON"};
        text[0] = 0;
        for (unsigned i = 0; i < 5; ++i) if (controls & (1u << i)) {
            if (text[0]) strcat(text, " + ");
            strcat(text, names[i]);
        }
        previous = controls;
    }
    static Ldp1450Text line;
    line.set(text, 86, 200);
    draw_singleline_LDP1450(renderer, g_ldp1450_font, line, {0,0,320,240}, picture, true);
}


std::recursive_mutex &mutex() { return yuv_mutex; }
void retire_texture(SDL_Texture *texture) { retired_textures.push_back(texture); }
void release_retired_textures() {
    for (auto *texture : retired_textures) SDL_DestroyTexture(texture);
    retired_textures.clear();
}
void release_renderer(SDL_Renderer *renderer) {
    SDL_DestroyTexture(g_ldp1450_font); g_ldp1450_font = nullptr;
    calculated_moves_enabled = false;
    for (auto &line : g_ldp1450_lines) line.dirty = true;
    SDL_DestroyTexture(crt_texture); crt_texture = nullptr;
    crt_width = crt_height = failed_width = failed_height = 0;
    android_crt_reset(renderer);
}

bool mobile_display() { return mobile; }
void drawable_size(SDL_Window *window, SDL_Rect &size) {
    if (mobile) SDL_GetWindowSizeInPixels(window, &size.w, &size.h);
}
bool resized(SDL_Window *window, bool fullscreen, SDL_Rect &size) {
    int w = 0, h = 0;
    if (!mobile || !window || !fullscreen ||
            !SDL_GetWindowSizeInPixels(window, &w, &h) || w <= 0 || h <= 0 ||
            (size.w == w && size.h == h)) return false;
    size = {0,0,w,h};
    LOGI << "Android mobile drawable resized: " << w << "x" << h;
    return true;
}
bool direct_render(SDL_Renderer *renderer, const SDL_Rect &output,
                   const SDL_Rect &picture, bool rotated) {
    const bool direct = !rotated && picture.x >= 0 && picture.y >= 0 &&
        picture.x+picture.w <= output.w && picture.y+picture.h <= output.h;
    static int previous = -1;
    if (previous != static_cast<int>(direct)) {
        LOGI << "Android rendering: " << (direct ? "direct" : "intermediate texture")
             << " (" << SDL_GetRendererName(renderer) << ", " << output.w << "x" << output.h << ")";
        previous = static_cast<int>(direct);
    }
    return direct;
}
SDL_Texture *game_target(SDL_Renderer *renderer, const SDL_Rect &output,
                         bool crt, bool linear) {
    if (!crt) failed_width = failed_height = 0;
    if (crt && android_crt_available(renderer) &&
            (failed_width != output.w || failed_height != output.h)) {
        if (!crt_texture || crt_width != output.w || crt_height != output.h) {
            SDL_Texture *next = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA32,
                SDL_TEXTUREACCESS_TARGET, output.w, output.h);
            if (next) {
                SDL_SetTextureBlendMode(next, SDL_BLENDMODE_NONE);
                SDL_SetTextureScaleMode(next, linear ? SDL_SCALEMODE_LINEAR : SDL_SCALEMODE_NEAREST);
                SDL_DestroyTexture(crt_texture); crt_texture = next;
                crt_width = output.w; crt_height = output.h;
            } else {
                LOGW << "CRT texture creation failed: " << SDL_GetError();
                failed_width = output.w; failed_height = output.h;
                SDL_DestroyTexture(crt_texture); crt_texture = nullptr;
            }
        }
        return crt_texture;
    }
    if (crt_texture) { SDL_DestroyTexture(crt_texture); crt_texture = nullptr; }
    return nullptr;
}
void present_game(SDL_Renderer *renderer, SDL_Texture *target) {
    if (!target) return;
    SDL_SetRenderTarget(renderer, nullptr);
    SDL_SetRenderClipRect(renderer, nullptr);
    SDL_RenderClear(renderer);
    if (!android_crt_present(renderer, target))
        SDL_RenderTexture(renderer, target, nullptr, nullptr);
}

bool init_text(SDL_Renderer *renderer, SDL_Surface *font, bool linear,
               const char *game, bool native_prompts) {
    // DL2 guidance also drives Watch Mode, but its ROM already draws the
    // prompt. Only games with calculated text get an additional move label.
    calculated_moves_enabled = !native_prompts && game &&
            (std::strcmp(game, "dle21") == 0 || std::strcmp(game, "ace") == 0);
    if (!native_prompts && !(arcade_visual_moves_enabled() && calculated_moves_enabled)) return true;
    g_ldp1450_font = SDL_CreateTextureFromSurface(renderer, font);
    if (!g_ldp1450_font) {
        LOGE << "Cannot create LDP1450 font: " << SDL_GetError();
        return false;
    }
    SDL_SetTextureBlendMode(g_ldp1450_font, SDL_BLENDMODE_BLEND);
    SDL_SetTextureScaleMode(g_ldp1450_font, linear ? SDL_SCALEMODE_LINEAR : SDL_SCALEMODE_NEAREST);
    return true;
}
void queue_text(unsigned slot, const char *text, int x, int y) {
    if (slot >= 3) return;
    rom_text_active = true;
    g_ldp1450_lines[slot].set(text, x, y);
}
bool has_rom_text() { return rom_text_active; }
void draw_game_text(SDL_Renderer *renderer, const SDL_FRect &canvas,
                    const SDL_FRect &picture) {
    for (auto &line : g_ldp1450_lines)
        draw_singleline_LDP1450(renderer, g_ldp1450_font, line, canvas, picture);
    draw_recorded_move(renderer, picture);
}
} } // namespace video::android_video
