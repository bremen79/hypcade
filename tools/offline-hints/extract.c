/* SPDX-License-Identifier: GPL-3.0-or-later
 * Laptop-only bounded branch explorer. No video, SDL, sleeping or wall clock.
 * Uses the vendored planner's snapshots and ROM input-window interpretation.
 */
#include "games/cinematronics/board.h"
static uint64_t simulated_cycles;
/* These ranges are inside the successful ending clips, not death/attract clips.
 * Only naturally executed, CRC-checked ROMs can reach them: no injected seeks. */
static bool offline_won(const CineBoard *b, const Ldp *ldp) {
    bool alive = (b->digits[6] > 0 && b->digits[6] <= 9) ||
                 (b->digits[7] > 0 && b->digits[7] <= 9);
    int first = b->game == CINE_DRAGONS_LAIR ? 31080 : 32840;
    return alive && ldp->state == LDP_PLAYING && ldp->frame >= first && ldp->frame <= first + 100;
}
#define HYPSEUS_OFFLINE_TERMINAL(board, ldp) offline_won(board, ldp)
static void counted_run(CineBoard *board, uint64_t cycles) {
    uint64_t before = board->cycles;
    cine_run(board, cycles);
    simulated_cycles += board->cycles - before;
}
#define cine_run counted_run
#include "games/cinematronics/autoplay.c"
#undef cine_run
#include <inttypes.h>
#include <errno.h>
#include "../../android/app/jni/arcade_signature.h"

#define MAX_NODES 4096
static Machine *pending;
static unsigned queued, dropped, evaluated, deaths, unknowns, ignored, positives;

static uint64_t headers_hash(const CineBoard *b) {
    return arcade_cine_signature(b->ram + MOVE_LIST, 256);
}
static void push(const Machine *m, unsigned capacity) {
    if (queued >= capacity) { ++dropped; return; }
    pending[queued] = *m;
    connect_machine(&pending[queued++]);
}
/* Return the specific live ROM timer record for this candidate. Timers are
 * nominal IRQ ticks, not proven press boundaries. Each trial tests one instant. */
static void advance_after_move(Machine *m, const Machine *before,
                               const CineMove *acted, int acted_count) {
    uint64_t end = m->board.cycles + 10 * (uint64_t)CINE_CPU_HZ;
    uint64_t headers = headers_hash(&before->board);
    int initial_lives = lives(&m->board);
    while (m->board.cycles < end && lives(&m->board) >= initial_lives) {
        CineMove now[16] = {{0}};
        int n = cine_open_moves(&m->board, now, 16);
        if (headers_hash(&m->board) != headers || !same_moves(now, n, acted, acted_count)) break;
        run_until(m, m->board.cycles + SLICE_CYCLES);
    }
}

static void emit(const Machine *m, CineMove move, Verdict v, unsigned node) {
    for (int e = 0; e < 16; ++e) {
        const uint8_t *x = m->board.ram + MOVE_LIST + 16 * e;
        if (!(x[0] & 128)) break;
        if (x[12] || (x[0] & 15) != move.input) continue;
        for (unsigned w = 0; w < (x[1] & 3); ++w) {
            if (!x[13+w]) continue;
            if (x[2+((x[1] >> (2+2*w)) & 3)] != move.outcome) break;
            printf("{\"type\":\"trial\",\"node\":%u,\"headers\":\"%016" PRIx64
                   "\",\"outcome\":%u,\"control\":%u,\"frame\":%d,"
                   "\"cycle\":%" PRIu64 ",\"entry\":%d,\"window\":%u,"
                   "\"remaining_ticks\":%u,\"verdict\":\"%s\"}\n",
                   node, headers_hash(&m->board), move.outcome, move.input ? move.input : 16,
                   m->ldp.frame, m->board.cycles, e, w, x[13+w],
                   v == SURVIVES ? "continuation" : v == DIES ? "death" :
                   v == IGNORED ? "ignored" : "unresolved");
            return;
        }
    }
}

int main(int argc, char **argv) {
    /* Arguments validated by the Python frontend; reject unsafe direct use. */
    if (argc != 8 && argc != 10) {
        fprintf(stderr, "usage: extract ROM GAME NODES DSW1 DSW2 SKILL SAMPLE_TICKS\n");
        return 2;
    }
    unsigned limit = (unsigned)strtoul(argv[3], NULL, 10);
    unsigned ticks = (unsigned)strtoul(argv[7], NULL, 10);
    if (!limit || limit > MAX_NODES || !ticks || ticks > 30) return 2;
    bool dle = strcmp(argv[2], "dle21") == 0;
    if (!dle && strcmp(argv[2], "ace") != 0) return 2;
    Machine root = {0};
    if (!cine_load_roms(&root.board, argv[1])) return 1;
    /* Hypseus initializes unmapped sockets to zero for this three-chip set. */
    if (dle) memset(root.board.rom + 0x6000, 0, 0x4000);
    ldp_init(&root.ldp, 24000.0 / 1001.0, 0);
    ldv1000_init(&root.player, &root.ldp, CINE_CPU_HZ);
    cine_reset(&root.board, cine_ldv1000_link(&root.player));
    /* Match this port's lair/ace constructors before optional raw DIP overrides. */
    root.board.dsw1 = dle ? 0x22 : 0x3d;
    root.board.dsw2 = dle ? 0xd8 : 0xfe;
    if (strcmp(argv[4], "default")) root.board.dsw1 = (uint8_t)strtoul(argv[4], NULL, 16);
    if (strcmp(argv[5], "default")) root.board.dsw2 = (uint8_t)strtoul(argv[5], NULL, 16);
    cine_set(&root.board, CINE_UNLIMITED_LIVES, false);
    cine_set(&root.board, CINE_FREE_PLAY, true);
    root.board.ay.rendering = false;
    double start = argc == 10 ? 68 + atof(argv[9]) : 68;
    while (root.board.cycles < (uint64_t)((start + 0.2) * CINE_CPU_HZ)) {
        double t = (double)root.board.cycles / CINE_CPU_HZ;
        root.board.inputs.start1 = t >= start;
        root.board.inputs.cadet = !strcmp(argv[6], "cadet") && t >= start;
        root.board.inputs.captain = !strcmp(argv[6], "captain") && t >= start;
        root.board.inputs.ace = !strcmp(argv[6], "ace") && t >= start;
        run_until(&root, root.board.cycles + SLICE_CYCLES);
    }
    memset(&root.board.inputs, 0, sizeof root.board.inputs);
    printf("{\"type\":\"config\",\"dsw1\":%u,\"dsw2\":%u,\"fps_num\":24000,\"fps_den\":1001}\n",
           root.board.dsw1, root.board.dsw2);
    if (argc == 10 && strcmp(argv[8], "campaign") == 0) {
        CineAutoplay ap;
        cine_autoplay_init(&ap, false);
        int initial_lives = lives(&root.board), last_moves = 0;
        uint64_t end = root.board.cycles + UINT64_C(3600) * CINE_CPU_HZ;
        while (root.board.cycles < end && !offline_won(&root.board, &root.ldp)) {
            cine_autoplay_play(&ap, &root.board, &root.ldp, &root.player);
            if (ap.moves_made != last_moves) {
                CineMove open[16]; int n = cine_open_moves(&root.board, open, 16);
                for (int i = 0; i < n; ++i) if (open[i].input == ap.pressing)
                    emit(&root, open[i], SURVIVES, ap.moves_made);
                last_moves = ap.moves_made;
                fprintf(stderr, "move=%d frame=%d lives=%d game_seconds=%.2f\n",
                        last_moves, root.ldp.frame, lives(&root.board),
                        (double)root.board.cycles / CINE_CPU_HZ);
                fflush(stdout);
            }
            if (lives(&root.board) < initial_lives) {
                fprintf(stderr, "CAMPAIGN FAILED: lost a life at frame %d after %d moves\n", root.ldp.frame, last_moves);
                cine_autoplay_free(&ap);
                return 3;
            }
            uint64_t next = cine_autoplay_next_event(&ap);
            uint64_t slice = SLICE_CYCLES;
            if (next > root.board.cycles && next - root.board.cycles < slice) slice = next - root.board.cycles;
            run_until(&root, root.board.cycles + slice);
        }
        bool won = offline_won(&root.board, &root.ldp);
        printf("{\"type\":\"summary\",\"nodes\":%d,\"trials\":%d,\"pending\":0,"
               "\"dropped\":0,\"simulated_cycles\":%" PRIu64 ",\"complete\":%s,"
               "\"completion_scope\":\"one death-free campaign\",\"victory_frame\":%d,"
               "\"lives_before\":%d,\"lives_after\":%d,\"late_inputs\":%d}\n",
               last_moves, last_moves, simulated_cycles, won ? "true" : "false", root.ldp.frame,
               initial_lives, lives(&root.board), ap.late_presses);
        cine_autoplay_free(&ap);
        if (!won) fprintf(stderr, "CAMPAIGN FAILED: victory not reached before safety timeout\n");
        return won ? 0 : 3;
    }
    pending = calloc(limit, sizeof *pending);
    Machine *p = calloc(1, sizeof *p), *trial = calloc(1, sizeof *trial);
    Machine *next = calloc(1, sizeof *next), *next_trial = calloc(1, sizeof *next_trial);
    Machine *after = calloc(1, sizeof *after), *primary = calloc(1, sizeof *primary);
    if (!pending || !p || !trial || !next || !next_trial || !after || !primary) return 1;
    push(&root, limit);
    unsigned expanded = 0, dead_ends = 0;
    while (queued && expanded < limit) {
        *p = pending[--queued]; connect_machine(p);
        ++expanded;
        uint64_t end = p->board.cycles + 10 * (uint64_t)CINE_CPU_HZ;
        int start_lives = lives(&p->board);
        CineMove seen[16] = {{0}}; int seen_count = 0;
        uint64_t stable_since = p->board.cycles, last_sample = 0, previous_hash = 0;
        bool found = false;
        while (p->board.cycles < end && lives(&p->board) >= start_lives) {
            CineMove open[16] = {{0}};
            int n = p->ldp.state == LDP_PLAYING && lives(&p->board) > 0
                ? cine_open_moves(&p->board, open, 16) : 0;
            uint64_t h = headers_hash(&p->board);
            if (!same_moves(open, n, seen, seen_count) || h != previous_hash) {
                memcpy(seen, open, sizeof seen); seen_count = n;
                previous_hash = h; stable_since = p->board.cycles; last_sample = 0;
            } else if (n && p->board.cycles - stable_since >= SETTLE_CYCLES &&
                       (!last_sample || p->board.cycles - last_sample >= ticks * UINT64_C(131072))) {
                last_sample = p->board.cycles;
                bool first = true;
                for (int i = 0; i < n; ++i) {
                    /* Each input is tested even when outcomes match. */
                    *trial = *p; connect_machine(trial);
                    Verdict v = try_move(trial, open[i].input, open, n, next, next_trial, after, 1);
                    ++evaluated; deaths += v == DIES; unknowns += v == UNRESOLVED;
                    ignored += v == IGNORED; positives += v == SURVIVES;
                    emit(p, open[i], v, expanded);
                    if (v == SURVIVES) {
                        advance_after_move(after, p, open, n);
                        if (first) { *primary = *after; connect_machine(primary); first = false; }
                        else push(after, limit);
                    }
                }
                if (!first) {
                    /* Explore later timing windows/no-input on a deferred branch,
                     * while going deeper along the first successful continuation. */
                    run_until(p, p->board.cycles + ticks * UINT64_C(131072));
                    push(p, limit);
                    if (queued == limit) { --queued; ++dropped; }
                    push(primary, limit);
                    found = true;
                    break;
                }
            }
            run_until(p, p->board.cycles + SLICE_CYCLES);
        }
        if (!found) {
            ++dead_ends;
            printf("{\"type\":\"no_input\",\"node\":%u,\"frame\":%d,"
                   "\"lives_before\":%d,\"lives_after\":%d}\n",
                   expanded, p->ldp.frame, start_lives, lives(&p->board));
            /* Keep following no-input through deaths, retries and long scenes. */
            if (lives(&p->board) > 0) push(p, limit);
        }
        fprintf(stderr, "nodes=%u/%u trials=%u continuations=%u pending=%u\n",
                expanded, limit, evaluated, positives, queued);
        fflush(stdout);
    }
    printf("{\"type\":\"summary\",\"nodes\":%u,\"trials\":%u,\"continuations\":%u,"
           "\"deaths\":%u,\"ignored\":%u,\"unresolved\":%u,\"pending\":%u,"
           "\"dropped\":%u,\"dead_ends\":%u,\"simulated_cycles\":%" PRIu64 ",\"complete\":false}\n",
           expanded, evaluated, positives, deaths, ignored, unknowns, queued, dropped, dead_ends, simulated_cycles);
    free(primary); free(after); free(next_trial); free(next); free(trial); free(p); free(pending);
    return 0;
}
