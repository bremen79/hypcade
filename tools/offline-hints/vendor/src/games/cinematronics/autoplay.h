/* Modified for Hypcade offline hint generation (2026-11-08).
 * See vendor/provenance.json and vendor/NOTICE for changes and original credits. */
// autoplay.h - let the program play the game by itself.
//
// The game keeps the moves it's waiting for in a list in RAM (see
// autoplay.c). Each entry names an input, the windows of time when it
// counts, and an outcome code for each window, but nothing says which
// outcome is good. So whenever a new set of moves opens, the autoplayer
// tries each one on a copy of the machine, runs the copy ahead (much faster
// than real time), and keeps the move after which the hero doesn't lose a
// life. It only plays the joystick and sword; coins, start and Space Ace's
// skill level are up to you.

#ifndef LV_CINE_AUTOPLAY_H
#define LV_CINE_AUTOPLAY_H

#include "games/cinematronics/board.h"
#include "ldp/ldp.h"
#include "ldp/ldv1000.h"

#include <stdbool.h>
#include <stdint.h>

#define CINE_AUTOPLAY_MAX_MOVES 16
#define CINE_AUTOPLAY_LIST_BYTES (16 * 12)  // the list's fixed parts (see autoplay.c)
#define CINE_AUTOPLAY_QUEUE 4                // how many moves to plan ahead

// A move the game will accept right now: an input (0 = sword, otherwise
// joystick bits 1 up, 2 down, 4 left, 8 right) and the outcome code it
// leads to.
typedef struct {
    uint8_t input;
    uint8_t outcome;
} CineMove;

// The next move to plan, with its own copy of the machine (see
// cine_autoplay_think).
typedef struct CineAutoplayJob CineAutoplayJob;

typedef struct {
    bool verbose;  // print each move made

    // The list of moves last planned for, and how far ahead that plan
    // looked: a new plan starts when the game writes a new list.
    uint8_t planned[CINE_AUTOPLAY_LIST_BYTES];
    uint64_t plan_until;

    bool thinking;        // a job is out being planned
    bool continuing;      // the job can plan further ahead
    unsigned generation;  // bumped whenever the plans are thrown away

    // The moves planned so far, in order: each with when to press it, and
    // a checksum of the state the game should be in at that moment.
    struct {
        int input;
        uint64_t press_at;
        uint32_t state;
    } queue[CINE_AUTOPLAY_QUEUE];
    int queued;

    int pressing;         // input being held, or -1
    uint64_t release_at;  // board cycle at which to let go

    int moves_made;
    int late_presses;     // moves pressed later than planned (the plan came back late)
    uint64_t latest;      // the latest, in cycles

    CineAutoplayJob *job;  // made when first needed (it's big: it holds the ROM)
} CineAutoplay;

void cine_autoplay_init(CineAutoplay *ap, bool verbose);
void cine_autoplay_free(CineAutoplay *ap);

// Start afresh after a break (the player took over for a while): judge
// whatever moves are open now, even if they were judged before. No job may
// be out being judged.
void cine_autoplay_resume(CineAutoplay *ap);

// Playing takes three steps, so the planning can happen on another thread
// while the game runs on, and the picture never waits for it:
//
//   cine_autoplay_update   Call often while the board runs, and at least at
//                          each cine_autoplay_next_event. It presses and
//                          releases moves on time (in board->inputs, on top
//                          of whatever the player presses), and returns a
//                          job when there's planning to do.
//   cine_autoplay_think    Plan one more move: run the job's copy of the
//                          machine ahead to the moment a move should be made,
//                          and choose it. Slow (tens of milliseconds, now
//                          and then much more), and safe on any thread, as it
//                          only touches the job.
//   cine_autoplay_answer   Back on the board's thread: queue the planned
//                          move.
//
// The job's copy carries on from each planned move, so the planning runs
// ahead of the game, a few moves at a time, and each move is ready long
// before it's due. Only the first move after starting (or after the game
// strays from the plan) can come late.
//
// ldp and player are the board's laserdisc player, copied with the board.
CineAutoplayJob *cine_autoplay_update(CineAutoplay *ap, CineBoard *board, const Ldp *ldp,
                                      const Ldv1000 *player);
void cine_autoplay_think(CineAutoplayJob *job);
void cine_autoplay_answer(CineAutoplay *ap, CineAutoplayJob *job);

// The board cycle of the next press or release, or UINT64_MAX. Run the
// board up to it and call cine_autoplay_update there, so each move is
// pressed exactly when it was judged to be.
uint64_t cine_autoplay_next_event(const CineAutoplay *ap);

// All three steps at once, judging on this thread: for tools that don't
// mind waiting.
void cine_autoplay_play(CineAutoplay *ap, CineBoard *board, const Ldp *ldp, const Ldv1000 *player);

// The moves the game will accept right now. Returns how many.
int cine_open_moves(const CineBoard *board, CineMove *moves, int max);

#endif
