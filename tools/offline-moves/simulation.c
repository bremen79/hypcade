/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later
 * Shared headless CPU/player setup. No video, SDL, sleeping or wall clock.
 * The ROM player and exact replay verifier use these machine helpers.
 */
#include "games/cinematronics/board.h"
#include <string.h>
#include "offline_board.h"
/* These ranges are inside the successful ending clips, not death/attract clips.
 * Only naturally executed, CRC-checked ROMs can reach them: no injected seeks. */
static bool offline_won(const CineBoard *b, const Ldp *ldp) {
    bool alive = (b->digits[6] > 0 && b->digits[6] <= 9) ||
                 (b->digits[7] > 0 && b->digits[7] <= 9);
    int first = b->game == CINE_SPACE_ACE ? 32840 : 31080;
    return alive && ldp->state == LDP_PLAYING && ldp->frame >= first && ldp->frame <= first + 100;
}
#define HYPSEUS_OFFLINE_TERMINAL(board, ldp) offline_won(board, ldp)
#define connect_machine original_connect_machine
#include "games/cinematronics/autoplay.c"
#undef connect_machine
static void connect_machine(Machine *m) {
    original_connect_machine(m);
    if(m->board.game==CINE_PR7820)m->board.laserdisc=offline_pr7820_link(&m->player);
}
#include <inttypes.h>
#include <errno.h>
#include "../../android/app/jni/arcade_signature.h"

static uint64_t headers_hash(const CineBoard *b) {
    return arcade_cine_signature(b->ram + MOVE_LIST, 256);
}
