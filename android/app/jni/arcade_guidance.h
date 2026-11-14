/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstddef>
#include <cstdint>
#include "arcade_move_policy.h"

void arcade_set_move_policy(int mode);
void arcade_configure_guidance(int mode, bool cue, bool watch);
bool arcade_hide_dl2_move_text(const char *game, unsigned x, unsigned y, unsigned line);

struct ArcadeMove {
    uint8_t controls = 0; // up, down, left, right, action
    bool ready = false;
    uint64_t window = 0;
};
ArcadeMove arcade_decode_cine(const uint8_t *memory, size_t size, bool ace, unsigned frame);
ArcadeMove arcade_decode_dl2(const uint8_t *memory, size_t size);
ArcadeMove arcade_decode_euro(const uint8_t *memory, size_t size, const char *game, unsigned frame);
void arcade_guidance_cine(const uint8_t *memory, size_t size, const char *game, bool playing, unsigned frame);
void arcade_guidance_dl2(const uint8_t *memory, size_t size, bool supported, bool playing);
void arcade_guidance_euro(const uint8_t *memory, size_t size, const char *game, bool playing, unsigned frame);

bool arcade_guidance_enabled();

bool arcade_visual_moves_enabled();
bool arcade_has_calculated_moves(const char *game);
bool arcade_watch_mode_enabled();
uint64_t arcade_guidance_snapshot();
uint64_t arcade_take_watch_move();
void arcade_set_watch_automation(bool active);
void arcade_request_current_watch_move();
void arcade_watch_publish_credits(int credits);
void arcade_watch_publish_coin_pending(bool pending);
void arcade_watch_publish_game_started(bool started);
unsigned arcade_visual_controls();
void arcade_configure_dl2_moves(uint8_t *memory, size_t size, bool visual);
