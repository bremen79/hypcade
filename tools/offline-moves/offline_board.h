/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef HYPCADE_OFFLINE_BOARD_H
#define HYPCADE_OFFLINE_BOARD_H
#include "games/cinematronics/board.h"
#include <string.h>

#define CINE_PR7820 ((CineGame)2)
typedef struct {
    const char *game;
    unsigned chips;
    const char *names[5];
    uint32_t crc[5];
    bool ace, pr7820;
    unsigned difficulties;
    uint8_t dsw1, dsw2;
} OfflineRom;
#include "rom_catalog.inc"
static inline const OfflineRom *offline_rom_by_game(const char *game) {
    for(unsigned i=0;i<sizeof offline_roms/sizeof *offline_roms;i++)
        if(!strcmp(offline_roms[i].game,game))return offline_roms+i;
    return NULL;
}
CineLaserdisc offline_pr7820_link(Ldv1000 *player);
#endif
