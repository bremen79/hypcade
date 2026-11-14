/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

// Read-only RAM adapters provide values; the existing scoreboard owns artwork,
// layout, dirty-digit detection and texture uploads. Invalid values are blank.
struct ScoreboardState {
    unsigned players = 0;
    unsigned score[2] = {};
    unsigned lives[2] = {};
    unsigned credits = 0;
};

template<class Board>
inline void update_scoreboard_state(Board &board, const ScoreboardState &state)
{
    for (unsigned player = 0; player < 2; ++player) {
        const bool participating = state.players <= 2 && player < state.players;
        unsigned score = state.score[player];
        const bool valid_score = participating && score <= 999999;
        for (int digit = 5; digit >= 0; --digit) {
            board.update_player_score(digit, valid_score ? score % 10 : 0xf, player);
            score /= 10;
        }
        const unsigned lives = state.lives[player];
        board.update_player_lives(
            participating && lives > 0 && lives <= 9 ? lives : 0xf, player);
    }
    board.update_credits(0, state.credits <= 99 ? state.credits / 10 : 0xf);
    board.update_credits(1, state.credits <= 99 ? state.credits % 10 : 0xf);
    board.RepaintIfNeeded();
}
