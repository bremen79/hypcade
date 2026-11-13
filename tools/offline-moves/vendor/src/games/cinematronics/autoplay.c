/* Modified for Hypcade offline move generation (2026-11-08).
 * See vendor/provenance.json and vendor/NOTICE for changes and original credits. */
#include "games/cinematronics/autoplay.h"

#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// ---------------------------------------------------------------------------
// The game's list of moves
// ---------------------------------------------------------------------------
//
// Found by watching Dragon's Lair rev F2 run; the fan sets for Dragon's Lair
// and Space Ace use the same list.
// While a scene plays, RAM from A0E0 holds 16-byte entries, one per input
// the game is watching for:
//
//   byte 0      bit 7: entry in use (a clear bit ends the list);
//               bits 0-3: the input (0 = sword, else joystick bits)
//   byte 1      bits 0-1: how many time windows follow (up to 3);
//               bits 2-7: for each window, 2 bits picking an outcome
//   bytes 2-5   outcome codes (FF = nothing happens)
//   byte 12     a delay before the windows start
//   bytes 13-15 the windows' lengths, in timer ticks (about 30 a second).
//               Only the first that isn't zero counts down: that's the
//               window open now.
//
// When the player presses an input whose entry has a window open, the game
// takes that window's outcome: the next stretch of the disc to play, a
// death scene or the way on.

#define MOVE_LIST 0x0E0  // A0E0, as an offset into the 2 KB of RAM
#define MOVE_ENTRY_SIZE 16
#define MOVE_LIST_MAX 16

int cine_open_moves(const CineBoard *b, CineMove *moves, int max)
{
    int n = 0;
    for (int e = 0; e < MOVE_LIST_MAX && n < max; e++) {
        const uint8_t *x = b->ram + MOVE_LIST + MOVE_ENTRY_SIZE * e;
        if (!(x[0] & 0x80)) break;
        if (x[12] != 0) continue;  // windows not started yet
        int windows = x[1] & 3;
        for (int w = 0; w < windows; w++) {
            if (x[13 + w] == 0) continue;  // this window is over
            uint8_t outcome = x[2 + ((x[1] >> (2 + 2 * w)) & 3)];
            if (outcome != 0xFF) moves[n++] = (CineMove){x[0] & 0x0F, outcome};
            break;
        }
    }
    return n;
}

static bool same_moves(const CineMove *a, int na, const CineMove *b, int nb)
{
    return na == nb && memcmp(a, b, (size_t)na * sizeof *a) == 0;
}

// ---------------------------------------------------------------------------
// Looking ahead
// ---------------------------------------------------------------------------

#define PRESS_SECONDS 0.1  // how long to hold a move (a few timer ticks)
#define SETTLE_CYCLES (CINE_CPU_HZ / 100)  // 10 ms
#define LOOKAHEAD_SECONDS 30.0  // how far to follow a move to see if it's fatal
#define PLAN_SECONDS 30.0      // how far ahead to look for the next move
#define SLICE_CYCLES (CINE_CPU_HZ / 1000)

// A copy of everything that decides what the game does next.
typedef struct {
    CineBoard board;
    Ldp ldp;
    Ldv1000 player;
} Machine;

struct CineAutoplayJob {
    Machine plan;    // runs ahead, from where the last planned move left off
    Machine trial;   // a copy of plan for each move tried
    Machine next_plan, next_trial;  // the same, one move further on
    Machine let_go;  // the trial when the chosen move is let go
    CineMove acted[CINE_AUTOPLAY_MAX_MOVES];  // the moves open when it was chosen
    int acted_count;
    bool carry_on;   // plan is where a planned move left off (not where the game was)
    unsigned generation;
    int choice;      // the verdict: the input to press, or -1 for none
    uint64_t press_at;  // and when
    uint32_t state;  // and a checksum of the state then
};

// A checksum of the state that decides what the game does next: RAM, the
// CPU's registers and the time. (Not the game's copy of the DIP switches at
// A010 and A011: the planning copy plays with lives that run out.)
static uint32_t state_checksum(const CineBoard *b)
{
    uint32_t h = 2166136261u;  // FNV-1a
    for (size_t i = 0; i < sizeof b->ram; i++)
        if (i != 0x010 && i != 0x011) h = (h ^ b->ram[i]) * 16777619u;
    const uint8_t *cpu = (const uint8_t *)&b->cpu;
    for (size_t i = 0; i < offsetof(Z80, bus); i++) h = (h ^ cpu[i]) * 16777619u;
    for (int i = 0; i < 8; i++) h = (h ^ (uint8_t)(b->cycles >> (8 * i))) * 16777619u;
    return h;
}

// Point a copied machine's parts at each other instead of at the originals'.
static void connect_machine(Machine *m)
{
    m->player.ldp = &m->ldp;
    m->board.laserdisc = cine_ldv1000_link(&m->player);
    m->board.cpu.bus.ctx = &m->board;
}

static void copy_machine(Machine *m, const CineBoard *board, const Ldp *ldp, const Ldv1000 *player)
{
    m->board = *board;
    m->ldp = *ldp;
    m->player = *player;
    connect_machine(m);
    // The copy plays on its own, without the real player's inputs.
    memset(&m->board.inputs, 0, sizeof m->board.inputs);
    // A lost life is how the copy shows a move was fatal, so it plays with
    // lives that run out even when the real game has unlimited ones.
    cine_set_now(&m->board, CINE_UNLIMITED_LIVES, false);
    // The copy makes no sound, and mustn't touch the original's samples.
    m->board.ay.rendering = false;
    m->board.ay.samples = NULL;
    m->board.ay.sample_count = m->board.ay.sample_capacity = 0;
}

static void set_input(CineInputs *in, int input, bool down)
{
    if (input == 0) {
        in->sword = down;
        return;
    }
    if (input & 1) in->up = down;
    if (input & 2) in->down = down;
    if (input & 4) in->left = down;
    if (input & 8) in->right = down;
}

// Lives left, from the score display (digit 6 for player 1, 7 for player
// 2; blank counts as none).
static int lives(const CineBoard *b)
{
    int n = 0;
    for (int i = 6; i <= 7; i++)
        if (b->digits[i] <= 9) n += b->digits[i];
    return n;
}

// The entries' fixed parts (bytes 0-11, not the timers). The game rewrites
// them when it writes a new list, or takes a move.
static void list_headers(const CineBoard *b, uint8_t out[MOVE_LIST_MAX * 12])
{
    memset(out, 0, MOVE_LIST_MAX * 12);
    for (int e = 0; e < MOVE_LIST_MAX; e++) {
        const uint8_t *x = b->ram + MOVE_LIST + MOVE_ENTRY_SIZE * e;
        memcpy(out + 12 * e, x, 12);
        if (!(x[0] & 0x80)) break;
    }
}

// Run the copy up to the given cycle (give or take one instruction).
static void run_until(Machine *m, uint64_t until)
{
    while (m->board.cycles < until) {
        uint64_t slice = until - m->board.cycles;
        cine_run(&m->board, slice < SLICE_CYCLES ? slice : SLICE_CYCLES);
        ldv1000_update(&m->player, m->board.cycles);
    }
}

typedef enum { DIES, SURVIVES, IGNORED, UNRESOLVED } Verdict;

// The game's input routine keeps a byte of flags per input, from A040: the
// sword, then each joystick direction code. Bits 6 and 7 mark a press it
// has seen (bit 5 is set at the first sighting, and the press counts at the
// next).
#define INPUT_FLAGS 0x040
#define INPUT_SEEN 0xC0

#define RETRY_CYCLES (CINE_CPU_HZ / 100)  // 10 ms

typedef enum { FOUND, DIED, GAVE_UP, WON } PlanResult;
#ifndef HYPSEUS_OFFLINE_TERMINAL
#define HYPSEUS_OFFLINE_TERMINAL(board, ldp) false
#endif

static PlanResult plan_moves(Machine *p, Machine *trial, Machine *next_plan, Machine *next_trial,
                             Machine *let_go, uint64_t until, bool stop_at_new_list, int depth, int *choice,
                             CineMove *acted, int *acted_count);

// Press the input on the copy now, hold it, and run on:
//
//   - The game doesn't see the press: it ignored it (it doesn't read the
//     joystick at every moment, even with a window open).
//   - The hero loses a life: the move is fatal. (After a fatal move the
//     list usually has no open moves until the death scene ends and the
//     life is gone.)
//   - The game takes the move, rewriting the list, and a new set of moves
//     opens: he survived. The game may take its time: it often stores the
//     move and only acts on it when the current stretch of the disc ends.
//
// A window running out on its own changes the open set too, but leaves the
// list as it was, so it doesn't count as moving on.
//
// Some fatal moves lead on to new moves anyway, and the hero dies a few
// seconds later whatever the player does. So with depth 1, a move only
// survives if the hero can then survive the next move too (judged at depth
// 0, using next_plan and next_trial).
//
// If let_go isn't NULL, it gets a copy of the machine at the moment the
// input is let go.
static Verdict try_move(Machine *m, int input, const CineMove *open, int open_count,
                        Machine *next_plan, Machine *next_trial, Machine *let_go, int depth)
{
    int start_lives = lives(&m->board);
    uint8_t start_headers[MOVE_LIST_MAX * 12], headers[MOVE_LIST_MAX * 12];
    list_headers(&m->board, start_headers);

    // Hold the input for exactly as long as the real board will (it's let
    // go at a set cycle), watching for the game to see it.
    uint64_t release = m->board.cycles + (uint64_t)(PRESS_SECONDS * CINE_CPU_HZ);
    bool seen = false;
    set_input(&m->board.inputs, input, true);
    while (m->board.cycles < release) {
        uint64_t slice = release - m->board.cycles;
        run_until(m, m->board.cycles + (slice < SLICE_CYCLES ? slice : SLICE_CYCLES));
        seen = seen || (m->board.ram[INPUT_FLAGS + input] & INPUT_SEEN);
    }
    set_input(&m->board.inputs, input, false);
    if (!seen) return IGNORED;
    if (let_go) {
        *let_go = *m;
        connect_machine(let_go);
    }

    bool taken = false;
    uint64_t end = release + (uint64_t)(LOOKAHEAD_SECONDS * CINE_CPU_HZ);
    while (m->board.cycles < end) {
        if (HYPSEUS_OFFLINE_TERMINAL(&m->board, &m->ldp)) return SURVIVES;
        if (lives(&m->board) < start_lives) return DIES;
        if (!taken) {
            list_headers(&m->board, headers);
            taken = memcmp(headers, start_headers, sizeof headers) != 0;
        }
        if (taken) {
            CineMove now[CINE_AUTOPLAY_MAX_MOVES];
            int n = cine_open_moves(&m->board, now, CINE_AUTOPLAY_MAX_MOVES);
            if (n > 0 && !same_moves(now, n, open, open_count)) {
                if (depth == 0) return SURVIVES;
                *next_plan = *m;
                connect_machine(next_plan);
                PlanResult r = plan_moves(next_plan, next_trial, NULL, NULL, NULL,
                                          m->board.cycles + (uint64_t)(PLAN_SECONDS * CINE_CPU_HZ),
                                          false, 0, NULL, NULL, NULL);
                return (r == FOUND || r == WON) ? SURVIVES : (r == DIED ? DIES : UNRESOLVED);
            }
        }
        run_until(m, m->board.cycles + SLICE_CYCLES);
    }
    // Still alive with the move taken, and no new moves by the time limit:
    // the end of the game, say.
    if (lives(&m->board) < start_lives) return DIES;
    return taken ? UNRESOLVED : IGNORED;
}

// Run the copy p ahead with no input, millisecond by millisecond, and
// whenever a new set of moves opens, try each move on a fresh copy (trial).
// FOUND: the first the hero survives is in *choice (if choice isn't NULL),
// to make at p's current cycle. DIED: the hero lost a life before any move
// could save him. GAVE_UP: neither, by until (or when the game wrote a new
// list, if stop_at_new_list).
//
// Moves only count while the scene plays (their windows count down then),
// and the game writes a list one entry at a time, so a set is only judged
// once it has been open for a moment. If the game ignores the moves (it
// isn't reading the joystick just then), they're tried again a little
// later.
static PlanResult plan_moves(Machine *p, Machine *trial, Machine *next_plan, Machine *next_trial,
                             Machine *let_go, uint64_t until, bool stop_at_new_list, int depth, int *choice,
                             CineMove *acted, int *acted_count)
{
    int start_lives = lives(&p->board);
    uint8_t start_headers[MOVE_LIST_MAX * 12], headers[MOVE_LIST_MAX * 12];
    list_headers(&p->board, start_headers);
    CineMove seen[CINE_AUTOPLAY_MAX_MOVES], decided[CINE_AUTOPLAY_MAX_MOVES];
    int seen_count = 0, decided_count = 0;
    if (acted && *acted_count > 0) {  // just acted on these: wait for them to change
        memcpy(seen, acted, sizeof seen);
        memcpy(decided, acted, sizeof decided);
        seen_count = decided_count = *acted_count;
    }
    uint64_t seen_since = p->board.cycles, retry_at = 0;

    while (p->board.cycles < until) {
        if (HYPSEUS_OFFLINE_TERMINAL(&p->board, &p->ldp)) return WON;
        if (lives(&p->board) < start_lives) return DIED;
        CineMove open[CINE_AUTOPLAY_MAX_MOVES];
        int n = p->ldp.state == LDP_PLAYING ? cine_open_moves(&p->board, open, CINE_AUTOPLAY_MAX_MOVES) : 0;
        if (!same_moves(open, n, seen, seen_count)) {
            memcpy(seen, open, sizeof open);
            seen_count = n;
            seen_since = p->board.cycles;
        } else if (p->board.cycles - seen_since >= SETTLE_CYCLES && p->board.cycles >= retry_at &&
                   !same_moves(open, n, decided, decided_count)) {
            memcpy(decided, open, sizeof open);
            decided_count = n;
            // Try each different outcome once.
            bool ignored = false;
            for (int i = 0; i < n; i++) {
                bool tried = false;
                for (int j = 0; j < i; j++) tried = tried || open[j].outcome == open[i].outcome;
                if (tried) continue;
                *trial = *p;
                connect_machine(trial);
                Verdict v = try_move(trial, open[i].input, open, n, next_plan, next_trial, let_go, depth);
                if (v == SURVIVES) {
                    if (choice) *choice = open[i].input;
                    if (acted) {
                        memcpy(acted, open, sizeof open);
                        *acted_count = n;
                    }
                    return FOUND;
                }
                ignored = ignored || v == IGNORED;
            }
            // Every move open now is fatal, or ignored. Wait for the next
            // window, and try ignored moves again in a moment.
            if (ignored) {
                decided_count = 0;
                retry_at = p->board.cycles + RETRY_CYCLES;
            }
        }
        if (stop_at_new_list) {
            list_headers(&p->board, headers);
            if (memcmp(headers, start_headers, sizeof headers) != 0) return GAVE_UP;
        }
        run_until(p, p->board.cycles + SLICE_CYCLES);
    }
    return GAVE_UP;
}

// Plan the next move. Starting from where the game was, give up if the game
// moves on by itself first (writes a new list after a move missed, say):
// planning starts again from the new list. Carrying on from a planned move,
// the list is bound to change, as the game takes that move.
void cine_autoplay_think(CineAutoplayJob *job)
{
    job->choice = -1;
    uint64_t until = job->plan.board.cycles + (uint64_t)(PLAN_SECONDS * CINE_CPU_HZ);
    if (plan_moves(&job->plan, &job->trial, &job->next_plan, &job->next_trial, &job->let_go, until,
                   !job->carry_on, 1, &job->choice, job->acted, &job->acted_count) != FOUND) {
        job->choice = -1;
        return;
    }
    job->press_at = job->plan.board.cycles;
    job->state = state_checksum(&job->plan.board);
    // The next call plans the move after this one, from the moment this one
    // is let go.
    job->plan = job->let_go;
    connect_machine(&job->plan);
    job->carry_on = true;
}

static const char *input_name(int input)
{
    static const char *names[16] = {
        "sword", "up", "down", "up+down", "left", "up+left", "down+left", "?",
        "right", "up+right", "down+right", "?", "?", "?", "?", "?",
    };
    return names[input & 15];
}

// ---------------------------------------------------------------------------
// Playing
// ---------------------------------------------------------------------------

void cine_autoplay_init(CineAutoplay *ap, bool verbose)
{
    memset(ap, 0, sizeof *ap);
    ap->verbose = verbose;
    ap->pressing = -1;
}

void cine_autoplay_free(CineAutoplay *ap)
{
    free(ap->job);
    ap->job = NULL;
}

// Throw the plans away (the game strayed from them), and plan again from
// where the game is.
static void forget_plans(CineAutoplay *ap)
{
    ap->queued = 0;
    ap->continuing = false;
    ap->generation++;  // a job still out being planned is now out of date
    memset(ap->planned, 0, sizeof ap->planned);
    ap->plan_until = 0;
}

void cine_autoplay_resume(CineAutoplay *ap)
{
    forget_plans(ap);
    ap->thinking = false;
    ap->pressing = -1;
}

CineAutoplayJob *cine_autoplay_update(CineAutoplay *ap, CineBoard *board, const Ldp *ldp,
                                      const Ldv1000 *player)
{
    // Holding a move: keep it down until it's time to let go.
    if (ap->pressing >= 0) {
        bool down = board->cycles < ap->release_at;
        set_input(&board->inputs, ap->pressing, down);
        if (down) return NULL;
        ap->pressing = -1;
    }

    // The next planned move: press it when its moment comes. If the game
    // isn't in the state the plan expected (the player pressed something
    // too, say), the plans are no good: start again.
    if (ap->queued > 0 && board->cycles >= ap->queue[0].press_at) {
        int input = ap->queue[0].input;
        uint64_t late = board->cycles - ap->queue[0].press_at;
        bool on_time = late <= (uint64_t)SLICE_CYCLES;
        if (on_time && state_checksum(board) != ap->queue[0].state) {
            forget_plans(ap);
            return NULL;
        }
        // (A plan that came back after its moment, on a slow computer: press
        // it now, a little later than planned, but usually still in time.)
        if (!on_time) {
            ap->late_presses++;
            if (late > ap->latest) ap->latest = late;
        }
        if (ap->verbose) {
            printf("%8.3f s  autoplay: %s at frame %d", (double)board->cycles / CINE_CPU_HZ,
                   input_name(input), ldp->frame);
            if (!on_time) printf(" (%.0f ms late)", late * 1000.0 / CINE_CPU_HZ);
            printf("\n");
        }
        memmove(&ap->queue[0], &ap->queue[1], (size_t)(ap->queued - 1) * sizeof ap->queue[0]);
        ap->queued--;
        ap->pressing = input;
        ap->release_at = board->cycles + (uint64_t)(PRESS_SECONDS * CINE_CPU_HZ);
        ap->moves_made++;
        set_input(&board->inputs, input, true);
        return NULL;
    }
    if (ap->thinking) return NULL;

    // Plan further ahead while there's room in the queue.
    if (ap->continuing && ap->queued < CINE_AUTOPLAY_QUEUE) {
        ap->thinking = true;
        return ap->job;
    }
    if (ap->queued > 0) return NULL;

    // Out of plans: start planning whenever the game writes a new list of
    // moves (or the last plan looked as far ahead as it could without
    // finding a move).
    uint8_t headers[MOVE_LIST_MAX * 12];
    list_headers(board, headers);
    if (memcmp(headers, ap->planned, sizeof headers) == 0 && board->cycles < ap->plan_until) return NULL;
    memcpy(ap->planned, headers, sizeof headers);
    if (!(headers[0] & 0x80)) {  // no moves in this list
        ap->plan_until = UINT64_MAX;
        return NULL;
    }
    if (!ap->job) ap->job = malloc(sizeof *ap->job);
    CineAutoplayJob *job = ap->job;
    copy_machine(&job->plan, board, ldp, player);
    job->carry_on = false;
    job->acted_count = 0;
    job->generation = ap->generation;
    ap->plan_until = board->cycles + (uint64_t)(PLAN_SECONDS * CINE_CPU_HZ);
    ap->thinking = true;
    return job;
}

void cine_autoplay_answer(CineAutoplay *ap, CineAutoplayJob *job)
{
    ap->thinking = false;
    if (job->generation != ap->generation || job->choice < 0) {  // out of date, or no move found
        ap->continuing = false;
        return;
    }
    ap->queue[ap->queued].input = job->choice;
    ap->queue[ap->queued].press_at = job->press_at;
    ap->queue[ap->queued].state = job->state;
    ap->queued++;
    ap->continuing = true;
}

uint64_t cine_autoplay_next_event(const CineAutoplay *ap)
{
    if (ap->pressing >= 0) return ap->release_at;
    if (ap->queued > 0) return ap->queue[0].press_at;
    return UINT64_MAX;
}

void cine_autoplay_play(CineAutoplay *ap, CineBoard *board, const Ldp *ldp, const Ldv1000 *player)
{
    CineAutoplayJob *job;
    while ((job = cine_autoplay_update(ap, board, ldp, player)) != NULL) {
        cine_autoplay_think(job);
        cine_autoplay_answer(ap, job);
    }
}
