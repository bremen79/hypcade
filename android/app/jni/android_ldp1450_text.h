/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <SDL3/SDL.h>
#include <algorithm>
#include <cstring>
#include <cmath>

namespace video {
// LDP1450 glyph mapping/spacing follows Hypseus (Matt Ownby, DirtBagXon).
// Retain geometry until the text or viewport changes; submit one SDL batch.
struct Ldp1450Text {
    char text[128] = {};
    int x = 0, y = 0, vertices = 0;
    bool dirty = true, previousFit = false;
    SDL_FRect previousCanvas = {}, previousViewport = {};
    SDL_Vertex mesh[127*4];
    int indices[127*6];

    void set(const char *value, int px, int py) {
        char trimmed[128] = {};
        size_t n = 0;
        while (n < sizeof(trimmed)-1 && value[n]) { trimmed[n] = value[n]; ++n; }
        while (n && trimmed[n-1] == ' ') trimmed[--n] = 0;
        if (x != px || y != py || std::strcmp(text, trimmed)) {
            std::memcpy(text, trimmed, sizeof(text)); x = px; y = py; dirty = true;
        }
    }
};

inline bool draw_singleline_LDP1450(SDL_Renderer *renderer, SDL_Texture *font,
                                   Ldp1450Text &line, const SDL_FRect &canvas,
                                   const SDL_FRect &viewport, bool fit = false) {
    if (!font || !line.text[0] || canvas.w <= 0 || canvas.h <= 0) return true;
    if (line.dirty || fit != line.previousFit || std::memcmp(&canvas, &line.previousCanvas, sizeof(canvas)) ||
            std::memcmp(&viewport, &line.previousViewport, sizeof(viewport))) {
        float fw, fh;
        if (!SDL_GetTextureSize(font, &fw, &fh)) return false;
        const size_t length = std::strlen(line.text);
        const float shrink = fit ? std::min(1.0f, (canvas.w-line.x-8)/(15*length+1)) : 1.0f;
        const float sx = viewport.w/canvas.w, sy = viewport.h/canvas.h;
        const float width = 16*sx*shrink, height = 16*sy*shrink;
        float x = viewport.x+(line.x-canvas.x)*sx;
        const float y = viewport.y+(line.y-canvas.y)*sy;
        line.vertices = 0;
        for (size_t i=0; i<length; ++i, x+=15*sx*shrink) {
            const unsigned c = static_cast<unsigned char>(line.text[i]);
            const int glyph = c>=0x26 && c<=0x39 ? c-0x25
                            : c>='A' && c<='Z' ? c-0x2a : c==0x13 ? 0x32 : 0x31;
            if (glyph == 0x31) continue; // Transparent space, including unknown characters.
            const float left = std::max(x, viewport.x), top = std::max(y, viewport.y);
            const float right = std::min(x+width, viewport.x+viewport.w);
            const float bottom = std::min(y+height, viewport.y+viewport.h);
            if (right<=left || bottom<=top) continue;
            // SDL software truncates UV*atlas size: preserve integer glyph
            // edges against division roundoff with one normalized float ULP.
            const float u = std::nextafter( (glyph*16+(left-x)/width*16)/fw, 1.0f);
            const float v = std::nextafter( (top-y)/height*16/fh, 1.0f);
            const float u2 = std::nextafter( (glyph*16+(right-x)/width*16)/fw, 1.0f);
            const float v2 = std::nextafter( (bottom-y)/height*16/fh, 1.0f);
            const int base = line.vertices;
            const SDL_FColor white = {1,1,1,1};
            line.mesh[base]   = {{left,top}, white, {u,v}};
            line.mesh[base+1] = {{right,top}, white, {u2,v}};
            line.mesh[base+2] = {{left,bottom}, white, {u,v2}};
            line.mesh[base+3] = {{right,bottom}, white, {u2,v2}};
            const int order[] = {0,1,2,2,1,3};
            for (int j=0; j<6; ++j) line.indices[base/4*6+j] = base+order[j];
            line.vertices += 4;
        }
        line.previousCanvas = canvas; line.previousViewport = viewport; line.previousFit = fit; line.dirty = false;
    }
    return !line.vertices || SDL_RenderGeometry(renderer, font, line.mesh,
        line.vertices, line.indices, line.vertices/4*6);
}
} // namespace video
