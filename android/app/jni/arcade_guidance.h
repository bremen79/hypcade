// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstddef>
#include <cstdint>

struct ArcadeMove {
    uint8_t controls = 0; // up, down, left, right, action
    bool ready = false;
    uint64_t window = 0;
};
ArcadeMove arcade_decode_cine(const uint8_t *memory, size_t size, bool ace, unsigned frame);
ArcadeMove arcade_decode_dl2(const uint8_t *memory, size_t size);
void arcade_guidance_cine(const uint8_t *memory, size_t size, const char *game, bool playing, unsigned frame);
void arcade_guidance_dl2(const uint8_t *memory, size_t size, bool supported, bool playing);

bool arcade_guidance_enabled();

bool arcade_visual_hints_enabled();
unsigned arcade_visual_controls();
void arcade_configure_dl2_hints(uint8_t *memory, size_t size, bool visual);
