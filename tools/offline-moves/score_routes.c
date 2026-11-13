/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later
 * Native-ROM input trials and exact replay for the ROM-table player. This program has
 * no SDL, video decoder, audio output, sleeps, or dependency on an Android SDK.
 *
 * The action model is deliberately explicit: a ROM-listed control is pressed
 * for 100 ms, released, and followed to the next stable changed input decision.
 * Trials require live score/progression evidence; exact replays check every
 * input and checkpoint without enumerating alternative gameplay branches.
 */
#include "simulation.c"

#include <float.h>
#include <limits.h>
#include <math.h>
#include <stddef.h>
#include <zlib.h>
#include "../../android/app/jni/arcade_move_policy.h"

#define SEARCH_MAX_NODES 100000U
#define STATE_KEY_CAPACITY 4096U
#define SEARCH_SECONDS 30U
#define WIN_SETTLE_SECONDS 10U
#define SCORE_STABLE_SECONDS 1U

typedef enum { ROUTE_DECISION, ROUTE_VICTORY, ROUTE_DEATH, ROUTE_UNRESOLVED, ROUTE_IGNORED } RoutePhase;

/* Only ROM is shared. These two byte ranges contain every other board member,
 * including CPU state, RAM, inputs, latches, AY registers, display and clocks.
 * Pointer repair is mandatory on restore. The byte ranges are never hashed or
 * written to a file: canonical keys below explicitly encode each value. */
typedef struct {
    unsigned char before_rom[offsetof(CineBoard, rom)];
    unsigned char after_rom[sizeof(CineBoard) - offsetof(CineBoard, ram)];
    Ldp ldp;
    Ldv1000 player;
} RouteSnapshot;

typedef struct {
    unsigned char bytes[STATE_KEY_CAPACITY];
    size_t used;
    uint64_t a, b;
} StateKey;

typedef struct {
    RouteSnapshot snapshot;
    uint64_t hash_a, hash_b;
    int score;
} RouteNode;

typedef struct {
    unsigned control;
    uint64_t press_cycle, release_cycle, until_cycle, headers;
    int frame, video_start;
    bool seen, life_lost, terminal_proof, progress_proof;
    int before, after, plain;
    unsigned timing, outcome;
} RouteEdge;

typedef struct {
    unsigned max_seconds, difficulty;
    double start_delay;
    const char *rom, *game, *skill, *replay;
} RouteOptions;

typedef struct {
    Machine base;
    RouteOptions options;
    uint64_t deadline, rom_a, rom_b;
    unsigned initial_lives;
    RouteNode *nodes;
    unsigned score_probes, ignored_early_exits, fused_trials;
    unsigned baseline_queries, baseline_fallbacks, progress_moves;
    uint64_t baseline_cycles;
    bool time_cap, transition_cap, score_unsettled;
} RouteGraph;

typedef struct {
    Machine *machine;
    int last_lives, minimum_lives, last_score;
    bool death, score_valid;
    uint64_t score_changed;
    int watched_input;
    uint8_t input_last;
    bool input_armed, input_seen;
} RouteMonitor;

typedef struct ScoreBaseline ScoreBaseline;
static void score_baseline_write(void *ctx);
static void score_trial_observe(RouteMonitor *monitor);
static RouteMonitor *route_monitor;
static bool prove_terminal(Machine *,const Machine *,RouteGraph *,RouteEdge *,bool);
static void (*original_board_write)(void *, uint16_t, uint8_t);

static int player_one_lives(const CineBoard *board) {
    return board->digits[6] <= 9 ? board->digits[6] : -1;
}

/* Digits 0..5 are E038..E03D, left to right; E030..E035 are player two.
 * A blank leading digit is zero. Non-decimal diagnostics are not a score. */
static bool player_one_score(const CineBoard *board, int *score) {
    int value = 0;
    bool any = false, started = false;
    for (int i = 0; i < 6; ++i) {
        unsigned digit = board->digits[i];
        if (digit == 15 && !started) digit = 0;
        else if (digit > 9) return false;
        else { any = true; started = true; }
        value = value * 10 + (int)digit;
    }
    if (!any) return false;
    *score = value;
    return true;
}

static void monitor_observe(RouteMonitor *monitor) {
    const CineBoard *board = &monitor->machine->board;
    int current = player_one_lives(board);
    if (current >= 0) {
        if (monitor->last_lives >= 0 && current < monitor->last_lives) monitor->death = true;
        if (current < monitor->minimum_lives) monitor->minimum_lives = current;
        monitor->last_lives = current;
    }
    int score = 0;
    bool valid = player_one_score(board, &score);
    if (!valid || !monitor->score_valid || score != monitor->last_score)
        monitor->score_changed = board->cycles;
    monitor->last_score = score;
    monitor->score_valid = valid;
}

/* Observe actual score-display writes, including a life lost and replenished
 * within the same simulation slice. This delegates unchanged to the board. */
static void monitored_board_write(void *ctx, uint16_t address, uint8_t value) {
    original_board_write(ctx, address, value);
    if (address >= 0xe000 && (address & 0x38) == 0x38) score_baseline_write(ctx);
    if (!route_monitor || ctx != &route_monitor->machine->board) return;
    if (address >= 0xe000 && (address & 0x38) == 0x38) monitor_observe(route_monitor);
    if (route_monitor->watched_input >= 0 && address >= 0xa000 && address < 0xc000 &&
        (address & 0x7ff) == INPUT_FLAGS + route_monitor->watched_input) {
        uint8_t now = route_monitor->machine->board.ram[INPUT_FLAGS + route_monitor->watched_input];
        /* A sticky seen bit left by an earlier press is not acknowledgment of
         * this press. Observe fresh clear/debounce transitions at each write,
         * so a clear and set within one CPU slice are not missed. */
        if (!(now & INPUT_SEEN) || ((now & 0x20) && !(route_monitor->input_last & 0x20)))
            route_monitor->input_armed = true;
        if (route_monitor->input_armed && (now & INPUT_SEEN) &&
            (now & INPUT_SEEN) != (route_monitor->input_last & INPUT_SEEN)) route_monitor->input_seen = true;
        route_monitor->input_last = now;
    }
}

static void monitor_start(RouteMonitor *monitor, Machine *machine) {
    memset(monitor, 0, sizeof *monitor);
    monitor->machine = machine;
    monitor->watched_input = -1;
    monitor->last_lives = player_one_lives(&machine->board);
    monitor->minimum_lives = monitor->last_lives;
    monitor->score_changed = machine->board.cycles;
    monitor->score_valid = player_one_score(&machine->board, &monitor->last_score);
    route_monitor = monitor;
}

static void snapshot_save(RouteSnapshot *snapshot, const Machine *machine) {
    memcpy(snapshot->before_rom, &machine->board, sizeof snapshot->before_rom);
    memcpy(snapshot->after_rom, machine->board.ram, sizeof snapshot->after_rom);
    snapshot->ldp = machine->ldp;
    snapshot->player = machine->player;
}

static void snapshot_restore(Machine *machine, const RouteSnapshot *snapshot, const RouteGraph *graph) {
    memcpy(&machine->board, snapshot->before_rom, sizeof snapshot->before_rom);
    memcpy(machine->board.rom, graph->base.board.rom, sizeof machine->board.rom);
    memcpy(machine->board.ram, snapshot->after_rom, sizeof snapshot->after_rom);
    machine->board.cpu.bus=graph->base.board.cpu.bus;
    machine->board.switches=graph->base.board.switches;
    machine->board.ay.samples=NULL;
    machine->ldp = snapshot->ldp;
    machine->player = snapshot->player;
    connect_machine(machine);
}

static void key_bytes(StateKey *key, const void *bytes, size_t count) {
    if (count > sizeof key->bytes - key->used) {
        fprintf(stderr, "Internal error: canonical state key overflow\n");
        exit(1);
    }
    memcpy(key->bytes + key->used, bytes, count);
    key->used += count;
}
static void key_uint(StateKey *key, uint64_t value, unsigned count) {
    unsigned char bytes[8];
    for (unsigned i = 0; i < count; ++i) { bytes[i] = (unsigned char)value; value >>= 8; }
    key_bytes(key, bytes, count);
}
static void key_double(StateKey *key, double value) {
    _Static_assert(sizeof(double) == 8 && DBL_MANT_DIG == 53, "IEEE-754 double required");
    uint64_t bits; memcpy(&bits, &value, sizeof bits); key_uint(key, bits, 8);
}
static void key_float(StateKey *key, float value) {
    _Static_assert(sizeof(float) == 4 && FLT_MANT_DIG == 24, "IEEE-754 float required");
    uint32_t bits; memcpy(&bits, &value, sizeof bits); key_uint(key, bits, 4);
}
static void hash_bytes(const unsigned char *bytes, size_t length, uint64_t *a, uint64_t *b) {
    *a = UINT64_C(14695981039346656037);
    *b = UINT64_C(7809847782465536322);
    for (size_t i = 0; i < length; ++i) {
        *a = (*a ^ bytes[i]) * UINT64_C(1099511628211);
        *b = (*b ^ bytes[i]) * UINT64_C(14029467366897019727);
    }
}

/* The key includes all mutable machine fields, including absolute clock and
 * protocol phase. It intentionally does NOT coalesce merely similar rooms,
 * RAM headers, scores or disc frames. Padding, pointers and host byte order do
 * not participate. Hash collisions are checked against complete key bytes. */
static void machine_key(StateKey *key, const Machine *m, const RouteGraph *graph, RoutePhase phase) {
    memset(key, 0, sizeof *key);
    key_bytes(key, "HYPCADE_STATE_1", 15);
    key_uint(key, graph->rom_a, 8); key_uint(key, graph->rom_b, 8);
    key_uint(key, phase, 1); key_uint(key, m->board.game, 1);
    const Z80 *cpu = &m->board.cpu;
#define K8(field) key_uint(key, cpu->field, 1)
    K8(a); K8(f); K8(b); K8(c); K8(d); K8(e); K8(h); K8(l);
    K8(a2); K8(f2); K8(b2); K8(c2); K8(d2); K8(e2); K8(h2); K8(l2);
    K8(ixh); K8(ixl); K8(iyh); K8(iyl);
    key_uint(key, cpu->sp, 2); key_uint(key, cpu->pc, 2);
    K8(i); K8(r); key_uint(key, cpu->wz, 2);
    K8(iff1); K8(iff2); K8(im); K8(halted); K8(irq); K8(irq_data);
    K8(nmi); K8(irq_taken); K8(ei_pending); K8(q); K8(flags_changed);
#undef K8
    key_bytes(key, m->board.ram, sizeof m->board.ram);
    key_uint(key, m->board.dsw1, 1); key_uint(key, m->board.dsw2, 1);
    const CineInputs *inputs = &m->board.inputs;
#define IN(field) key_uint(key, inputs->field, 1)
    IN(up); IN(down); IN(left); IN(right); IN(sword); IN(start1); IN(start2);
    IN(coin1); IN(coin2); IN(cadet); IN(captain); IN(ace);
#undef IN
    const Ay8910 *ay = &m->board.ay;
    key_bytes(key, ay->regs, sizeof ay->regs);
    key_double(key, ay->ticks_per_cycle); key_double(key, ay->samples_per_tick);
    key_uint(key, ay->time, 8); key_double(key, ay->tick_carry);
    for (int i = 0; i < 3; ++i) { key_uint(key, ay->tone_count[i], 2); key_uint(key, ay->tone_high[i], 1); }
    key_uint(key, ay->noise_count, 1); key_uint(key, ay->noise_shift, 4);
    key_uint(key, ay->envelope_count, 2); key_uint(key, ay->envelope_step, 1);
    key_uint(key, ay->envelope_rising, 1); key_uint(key, ay->envelope_holding, 1);
    key_uint(key, ay->envelope_hold_level, 1); key_uint(key, ay->half_tick, 1);
    key_uint(key, ay->rendering, 1); key_double(key, ay->mix_sum);
    key_uint(key, (uint32_t)ay->mix_count, 4); key_double(key, ay->sample_phase);
    key_float(key, ay->dc_in); key_float(key, ay->dc_out);
    key_uint(key, (uint32_t)ay->sample_count, 4); key_uint(key, (uint32_t)ay->sample_capacity, 4);
    key_uint(key, m->board.ay_select, 1); key_uint(key, m->board.ld_latch, 1);
    key_uint(key, m->board.misc, 1); key_bytes(key, m->board.digits, sizeof m->board.digits);
    key_uint(key, m->board.lamps, 1); key_uint(key, m->board.cycles, 8);
    key_uint(key, m->board.next_irq, 8);
    const Ldp *ldp = &m->ldp;
    key_uint(key, ldp->state, 1); key_uint(key, (uint32_t)ldp->frame, 4);
    key_double(key, ldp->fps); key_double(key, ldp->speed); key_uint(key, ldp->blank_during_search, 1);
    key_double(key, ldp->frame_clock); key_double(key, ldp->search_clock);
    key_uint(key, (uint32_t)ldp->search_target, 4);
    const Ldv1000 *player = &m->player;
    key_double(key, player->clock_hz); key_uint(key, player->last, 8);
    key_uint(key, player->status, 1); key_bytes(key, player->digits, sizeof player->digits);
    key_uint(key, (uint32_t)player->digit_count, 4); key_uint(key, (uint32_t)player->autostop_frame, 4);
    key_uint(key, player->resume_at, 8); key_uint(key, player->status_before_stop, 1);
    key_uint(key, player->previous_state, 1); key_uint(key, player->audio[0], 1);
    key_uint(key, player->audio[1], 1); key_uint(key, player->muted, 1);
    key_uint(key, (uint32_t)player->reply_frame, 4); key_uint(key, (uint64_t)player->reply_field, 8);
    key_uint(key, player->last_command, 1); key_uint(key, player->konami_rom, 1);
    hash_bytes(key->bytes, key->used, &key->a, &key->b);
}

static void key_text(char text[33], uint64_t a, uint64_t b) {
    snprintf(text, 33, "%016" PRIx64 "%016" PRIx64, a, b);
}

typedef struct { uint64_t headers; CineMove moves[16]; int count; } DecisionKey;
static unsigned move_branch(const Machine *machine) {
    return machine->board.game==CINE_SPACE_ACE ?
        ((unsigned)machine->board.ram[0x16]<<8) | machine->board.ram[0x35] : 0;
}
static uint64_t move_signature(const Machine *machine) {
    return arcade_move_signature(machine->board.ram+MOVE_LIST,256,move_branch(machine));
}
static void decision_key(DecisionKey *key, const Machine *machine) {
    memset(key, 0, sizeof *key);
    key->headers = headers_hash(&machine->board);
    if (machine->ldp.state == LDP_PLAYING)
        key->count = cine_open_moves(&machine->board, key->moves, 16);
}
static bool same_decision(const DecisionKey *a, const DecisionKey *b) {
    return a->headers == b->headers && same_moves(a->moves, a->count, b->moves, b->count);
}

static void monitored_run(Machine *machine, uint64_t until, RouteMonitor *monitor) {
    while (machine->board.cycles < until && !monitor->death) {
        uint64_t slice = until - machine->board.cycles;
        if (slice > SLICE_CYCLES) slice = SLICE_CYCLES;
        run_until(machine, machine->board.cycles + slice);
        monitor_observe(monitor);
        score_trial_observe(monitor);
    }
}

/* The inherited ending marker is a known victory-clip range, not an unknown
 * RAM game-over flag. Allow bonuses/display writes to settle for ten seconds,
 * then require one second of numeric, unchanged P1 score and no life loss.
 * The emitted score_scope names this finite endpoint explicitly. */
static RoutePhase settle_victory(Machine *machine, RouteGraph *graph, RouteMonitor *monitor) {
    uint64_t finish = machine->board.cycles + (uint64_t)WIN_SETTLE_SECONDS * CINE_CPU_HZ;
    if (finish > graph->deadline) { graph->time_cap = true; return ROUTE_UNRESOLVED; }
    monitored_run(machine, finish, monitor);
    if (monitor->death) return ROUTE_DEATH;
    if (!monitor->score_valid || player_one_lives(&machine->board) <= 0 ||
        machine->board.cycles - monitor->score_changed < (uint64_t)SCORE_STABLE_SECONDS * CINE_CPU_HZ) {
        graph->score_unsettled = true;
        return ROUTE_UNRESOLVED;
    }
    return ROUTE_VICTORY;
}

/* Advance released input to a stable decision. After an observed press, don't
 * press the same still-open decision repeatedly: wait for its list/window to
 * change (a search/no-open interval also counts). Ignored presses may retry.
 * This restriction is part of the macro-action model, never an optimality claim. */
static RoutePhase seek_decision(Machine *machine, RouteGraph *graph, RouteMonitor *monitor,
                                const DecisionKey *previous, bool block_previous,
                                bool already_stable, uint64_t transition_end) {
    DecisionKey last; decision_key(&last, machine);
    uint64_t stable = machine->board.cycles;
    if (already_stable && previous && same_decision(previous, &last))
        stable = stable >= SETTLE_CYCLES ? stable - SETTLE_CYCLES : 0;
    while (true) {
        if (monitor->death || player_one_lives(&machine->board) == 0) return ROUTE_DEATH;
        if (offline_won(&machine->board, &machine->ldp)) return settle_victory(machine, graph, monitor);
        if (machine->board.cycles >= graph->deadline) { graph->time_cap = true; return ROUTE_UNRESOLVED; }
        if (machine->board.cycles >= transition_end) { graph->transition_cap = true; return ROUTE_UNRESOLVED; }
        DecisionKey now; decision_key(&now, machine);
        if (!same_decision(&last, &now)) { last = now; stable = machine->board.cycles; }
        if (block_previous && (!now.count || !same_decision(previous, &now))) block_previous = false;
        if (!block_previous && now.count && player_one_lives(&machine->board) > 0 && monitor->score_valid &&
            machine->board.cycles - stable >= SETTLE_CYCLES) return ROUTE_DECISION;
        uint64_t until = machine->board.cycles + SLICE_CYCLES;
        if (until > transition_end) until = transition_end;
        if (until > graph->deadline) until = graph->deadline;
        monitored_run(machine, until, monitor);
    }
}

static bool control_open(const DecisionKey *key, unsigned control) {
    if (!control) return true;
    int input = control == 16 ? 0 : (int)control;
    for (int i = 0; i < key->count; ++i)
        if (key->moves[i].input == input) return true;
    return false;
}

static RoutePhase route_transition(Machine *machine, RouteGraph *graph, unsigned control, RouteEdge *edge) {
    RouteMonitor monitor; monitor_start(&monitor, machine);
    DecisionKey before; decision_key(&before, machine);
    edge->control = control;
    edge->press_cycle = machine->board.cycles;
    edge->release_cycle = machine->board.cycles;
    edge->frame = machine->ldp.frame;
    edge->video_start = machine->ldp.search_target;
    edge->headers = move_signature(machine);
    edge->seen = false; edge->life_lost = false;
    uint64_t transition_end = machine->board.cycles + (uint64_t)SEARCH_SECONDS * CINE_CPU_HZ;

    if (control) {
        int input = control == 16 ? 0 : (int)control;
        monitor.watched_input = input;
        monitor.input_last = machine->board.ram[INPUT_FLAGS + input];
        monitor.input_armed = !(monitor.input_last & INPUT_SEEN);
        uint64_t release = machine->board.cycles + (uint64_t)(PRESS_SECONDS * CINE_CPU_HZ);
        set_input(&machine->board.inputs, input, true);
        while (machine->board.cycles < release && !monitor.death && machine->board.cycles < graph->deadline) {
            uint64_t until = machine->board.cycles + SLICE_CYCLES;
            if (until > release) until = release;
            if (until > graph->deadline) until = graph->deadline;
            monitored_run(machine, until, &monitor);

        }
        set_input(&machine->board.inputs, input, false);
        monitor.watched_input = -1;
        edge->seen = monitor.input_seen;
        edge->release_cycle = machine->board.cycles;
        /* A press without a fresh acknowledgment cannot produce an edge.
         * Its continuation is discarded by every caller, so stop at release
         * instead of emulating the next decision/death. Keep the full hold:
         * late acknowledgment and transient deaths must still be observed. */
        if (!edge->seen) {
            edge->until_cycle = machine->board.cycles;
            edge->life_lost = monitor.death;
            route_monitor = NULL;
            if (monitor.death) return ROUTE_DEATH;
            if (machine->board.cycles < release) {
                graph->time_cap = true;
                return ROUTE_UNRESOLVED;
            }
            ++graph->ignored_early_exits;
            return ROUTE_IGNORED;
        }
    } else {
        uint64_t until = machine->board.cycles + UINT64_C(131072);
        if (until > graph->deadline) until = graph->deadline;
        monitored_run(machine, until, &monitor);
    }
    RoutePhase phase = seek_decision(machine, graph, &monitor, &before,
                                    control != 0 && edge->seen,
                                    control == 0, transition_end);
    edge->until_cycle = machine->board.cycles;
    edge->life_lost = monitor.death;
    route_monitor = NULL;
    return phase;
}

#include "score_trial.h"

/* Enumerate timed decisions in one released-input sweep. Only accepted,
 * life-preserving decisions become snapshots; milliseconds are never nodes.
 * Keep the first accepted press per control/window and an explicit wait edge. */
static unsigned move_timing(const Machine *m, unsigned control) {
    int input = control == 16 ? 0 : (int)control;
    for (unsigned e = 0; e < 16; ++e) {
        const uint8_t *x = m->board.ram + MOVE_LIST + 16 * e;
        if (!(x[0] & 128)) break;
        if (x[12] || (x[0] & 15) != input) continue;
        for (unsigned w = 0; w < (x[1] & 3); ++w) {
            if (!x[13+w]) continue;
            if(x[2+((x[1]>>(2+2*w))&3)]!=0xff)
                return x[13+w] | ((e * 3 + w) << 8);
            break;
        }
    }
    return 0;
}

/* A zero-score action is retained only with this stronger counterfactual:
 * this one pulse followed by NO further input reaches a death-free ending;
 * withholding the pulse loses a life. No survival oracle drives either copy. */
static bool prove_terminal(Machine *trial,const Machine *source,RouteGraph *graph,RouteEdge *edge,bool settled) {
    uint64_t end=source->board.cycles+30*(uint64_t)CINE_CPU_HZ;
    if(end>graph->deadline)end=graph->deadline;
    RouteMonitor monitor;monitor_start(&monitor,trial);
    while(!settled && !monitor.death && trial->board.cycles<end && !offline_won(&trial->board,&trial->ldp))
        monitored_run(trial,trial->board.cycles+SLICE_CYCLES,&monitor);
    if(monitor.death || (!settled && !offline_won(&trial->board,&trial->ldp))){route_monitor=NULL;return false;}
    if(!settled && settle_victory(trial,graph,&monitor)!=ROUTE_VICTORY){route_monitor=NULL;return false;}
    Machine plain=*source;connect_machine(&plain);RouteMonitor baseline;monitor_start(&baseline,&plain);
    while(!baseline.death && plain.board.cycles<trial->board.cycles && !offline_won(&plain.board,&plain.ldp))
        monitored_run(&plain,plain.board.cycles+SLICE_CYCLES,&baseline);
    route_monitor=NULL;
    if(!baseline.death)return false;
    int before=0,after=0,without=0;
    if(!player_one_score(&source->board,&before) || !player_one_score(&trial->board,&after))return false;
    if(!player_one_score(&plain.board,&without))without=before;
    edge->before=before;edge->after=after;edge->plain=without;
    edge->terminal_proof=true;edge->timing|=0x4000;edge->until_cycle=trial->board.cycles;
    fprintf(stderr,"necessary terminal move frame=%d control=%u score=%d->%d: input wins, withheld input dies\n",source->ldp.frame,edge->control,before,after);
    return true;
}

/* Coverage-only hashes: normalize entry order and compare left/right-swapped
 * input tables. Neither hash participates in gameplay lookup or state merges. */
static int compare_shape_row(const void *a,const void *b){return memcmp(a,b,5);}
static uint64_t input_shape(const Machine *machine,bool mirror) {
    unsigned char rows[16][5]={{0}};unsigned count=0;
    for(unsigned e=0;e<16;e++) {
        const uint8_t *x=machine->board.ram+MOVE_LIST+16*e;if(!(x[0]&128))break;
        rows[count][0]=mirror ? (x[0]&~12)|((x[0]&4)<<1)|((x[0]&8)>>1) : x[0];
        rows[count][1]=x[1]&3;
        for(unsigned w=0;w<(x[1]&3);w++)rows[count][2+w]=x[2+((x[1]>>(2+2*w))&3)];
        ++count;
    }
    qsort(rows,count,5,compare_shape_row);uint64_t a,b;hash_bytes(&rows[0][0],count*5,&a,&b);return a;
}

/* Score-free rescue is a second pass at a dead end of the score-only graph.
 * This avoids running a whole ending probe for optional zero-score inputs at
 * every ordinary scene. Waiting is replayed inline, without retaining states. */

static bool parse_unsigned(const char *text, uint64_t maximum, uint64_t *value) {
    if (!text[0] || text[0] == '-' || text[0] == '+') return false;
    char *end = NULL; errno = 0;
    unsigned long long parsed = strtoull(text, &end, 10);
    if (errno || !end || *end || parsed > maximum) return false;
    *value = (uint64_t)parsed; return true;
}
static bool parse_options(RouteOptions *options, int argc, char **argv) {
    if (argc<6 || argc>10 || (argc-6)%2) return false;
    memset(options,0,sizeof *options);
    options->rom=argv[1];options->game=argv[2];options->skill=argv[3];
    if (strcmp(options->game,"dle21") && strcmp(options->game,"ace")) return false;
    if (strcmp(options->skill,"cadet") && strcmp(options->skill,"captain") && strcmp(options->skill,"ace")) return false;
    uint64_t maximum;
    if (!parse_unsigned(argv[5],7200,&maximum) || !maximum) return false;
    options->max_seconds=(unsigned)maximum;
    char *end=NULL;errno=0;options->start_delay=strtod(argv[4],&end);
    if (errno || end==argv[4] || *end || !isfinite(options->start_delay) ||
        options->start_delay<0 || options->start_delay>60) return false;
    bool has_difficulty=false;
    for (int i=6;i<argc;i+=2) {
        if (!strcmp(argv[i],"--replay") && !options->replay) options->replay=argv[i+1];
        else if (!strcmp(argv[i],"--difficulty") && !has_difficulty) {
            if (!parse_unsigned(argv[i+1],3,&maximum)) return false;
            options->difficulty=(unsigned)maximum;has_difficulty=true;
        } else return false;
    }
    if (!strcmp(options->game,"dle21") && options->difficulty) return false;
    return true;
}

bool graph_boot(RouteGraph *graph) {
    Machine *machine = &graph->base;
    if (!cine_load_roms(&machine->board, graph->options.rom)) return false;
    bool dle = strcmp(graph->options.game, "dle21") == 0;
    if (machine->board.game != (dle ? CINE_DRAGONS_LAIR : CINE_SPACE_ACE)) {
        fprintf(stderr, "ROM game does not match requested game\n"); return false;
    }
    static const uint32_t dle_crc[] = {0x4f8af481, 0x5fca04c5, 0xc14f36b3};
    static const uint32_t ace_crc[] = {0x427522d0, 0x18d0262d, 0x4646832d, 0x57db2a79, 0x85cbcdc4};
    const uint32_t *expected = dle ? dle_crc : ace_crc;
    unsigned chips = dle ? 3 : 5;
    for (unsigned i = 0; i < chips; ++i) {
        if (crc32(0, machine->board.rom + i * 8192, 8192) != expected[i]) {
            fprintf(stderr, "Unsupported ROM revision: this route adapter requires %s exactly\n",
                    dle ? "Dragon's Lair Enhancement 2.1" : "Space Ace A3");
            return false;
        }
    }
    if (dle) memset(machine->board.rom + 0x6000, 0, 0x4000);
    hash_bytes(machine->board.rom, sizeof machine->board.rom, &graph->rom_a, &graph->rom_b);
    ldp_init(&machine->ldp, 24000.0 / 1001.0, 0);
    ldv1000_init(&machine->player, &machine->ldp, CINE_CPU_HZ);
    cine_reset(&machine->board, cine_ldv1000_link(&machine->player));
    original_board_write = machine->board.cpu.bus.write;
    machine->board.cpu.bus.write = monitored_board_write;
    machine->board.dsw1 = dle ? 0x22 : 0x3d;
    if (!dle) {
        static const uint8_t difficulty_bits[]={0x0c,4,8,0};
        machine->board.dsw1=(machine->board.dsw1&~0x0c)|difficulty_bits[graph->options.difficulty];
    }
    machine->board.dsw2 = dle ? 0xd8 : 0xfe;
    cine_set(&machine->board, CINE_UNLIMITED_LIVES, false);
    cine_set(&machine->board, CINE_FREE_PLAY, true);
    machine->board.ay.rendering = false;
    uint64_t start = (uint64_t)((68 + graph->options.start_delay) * CINE_CPU_HZ);
    uint64_t finish = start + CINE_CPU_HZ / 5;
    fprintf(stderr, "Booting %s with virtual CPU/player only; no media is opened\n", graph->options.game);
    while (machine->board.cycles < finish) {
        bool press = machine->board.cycles >= start;
        machine->board.inputs.start1 = press;
        machine->board.inputs.cadet = press && !strcmp(graph->options.skill, "cadet");
        machine->board.inputs.captain = press && !strcmp(graph->options.skill, "captain");
        machine->board.inputs.ace = press && !strcmp(graph->options.skill, "ace");
        run_until(machine, machine->board.cycles + SLICE_CYCLES);
    }
    memset(&machine->board.inputs, 0, sizeof machine->board.inputs);
    uint64_t active_until = machine->board.cycles + 10 * (uint64_t)CINE_CPU_HZ;
    while (player_one_lives(&machine->board) <= 0 && machine->board.cycles < active_until)
        run_until(machine, machine->board.cycles + SLICE_CYCLES);
    if (player_one_lives(&machine->board) <= 0) {
        fprintf(stderr, "Start failed: player one has no active lives\n"); return false;
    }
    graph->initial_lives = (unsigned)player_one_lives(&machine->board);
    graph->deadline = machine->board.cycles + (uint64_t)graph->options.max_seconds * CINE_CPU_HZ;
    RouteMonitor monitor; monitor_start(&monitor, machine);
    RoutePhase phase = seek_decision(machine, graph, &monitor, NULL, false, false,
                                    machine->board.cycles + (uint64_t)SEARCH_SECONDS * CINE_CPU_HZ);
    route_monitor = NULL;
    if (phase != ROUTE_DECISION) {
        fprintf(stderr, "Start failed: no live input decision before death/timeout\n"); return false;
    }
    /* Config describes the replay root. The monitor above has already rejected
     * any life loss between Start and this first actionable state. */
    graph->initial_lives = (unsigned)player_one_lives(&machine->board);
    RouteNode *node=&graph->nodes[0];
    snapshot_save(&node->snapshot,machine);
    StateKey root;machine_key(&root,machine,graph,phase);
    node->hash_a=root.a;node->hash_b=root.b;
    player_one_score(&machine->board,&node->score);
    fprintf(stderr, "Player one active: lives=%u score=%d frame=%d root_cycle=%" PRIu64 "\n",
            graph->initial_lives, graph->nodes[0].score, machine->ldp.frame, machine->board.cycles);
    return true;
}

static bool valid_hash(const char *text) {
    if (strlen(text) != 32) return false;
    for (int i = 0; i < 32; ++i) if (!((text[i] >= '0' && text[i] <= '9') || (text[i] >= 'a' && text[i] <= 'f'))) return false;
    return true;
}
static bool hash_matches(const char *expected, uint64_t a, uint64_t b) {
    char actual[33]; key_text(actual, a, b); return strcmp(expected, actual) == 0;
}

int graph_replay(RouteGraph *graph) {
    FILE *file = fopen(graph->options.replay, "r");
    if (!file) { perror("replay trace"); return 1; }
    char line[512], version[32], root_hash[33], final_hash[33], extra;
    unsigned steps, expected_moves, moves = 0;
    int expected_score;
    if (!fgets(line, sizeof line, file) ||
        sscanf(line, "%31s %32s %32s %u %d %u %c", version, root_hash, final_hash, &steps, &expected_score, &expected_moves, &extra) != 6 ||
        strcmp(version, "HYPCADE_ROUTE_V2") || !valid_hash(root_hash) || !valid_hash(final_hash) ||
        steps > SEARCH_MAX_NODES ||
        expected_score < 0 || expected_score > 999999 || expected_moves > steps ||
        !hash_matches(root_hash, graph->nodes[0].hash_a, graph->nodes[0].hash_b)) {
        fprintf(stderr, "Invalid replay header or root checkpoint mismatch\n"); fclose(file); return 3;
    }
    Machine machine; snapshot_restore(&machine, &graph->nodes[0].snapshot, graph);
    RoutePhase phase = ROUTE_DECISION;
    StateKey key; machine_key(&key, &machine, graph, phase);
    for (unsigned i = 0; i < steps; ++i) {
        unsigned control, terminal_proof; uint64_t press, release, until;
        char from[33], to[33];
        if (!fgets(line, sizeof line, file) ||
            sscanf(line, "%u %" SCNu64 " %" SCNu64 " %" SCNu64 " %32s %32s %u %c",
                   &control, &press, &release, &until, from, to, &terminal_proof, &extra) != 7 ||
            (control && control!=1 && control!=2 && control!=4 && control!=8 && control!=16) || terminal_proof>1 || !valid_hash(from) || !valid_hash(to) || phase != ROUTE_DECISION ||
            !hash_matches(from, key.a, key.b)) {
            fprintf(stderr, "Invalid replay step/source checkpoint at step %u\n", i); fclose(file); return 3;
        }
        if (press < machine.board.cycles) { fclose(file); return 3; }
        RouteMonitor waiting; monitor_start(&waiting,&machine);
        monitored_run(&machine,press,&waiting);route_monitor=NULL;
        if(waiting.death){fclose(file);return 3;}
        DecisionKey decision; decision_key(&decision, &machine);
        if (!control_open(&decision, control)) {
            fprintf(stderr, "Replay input is not listed by the live ROM at step %u\n", i); fclose(file); return 3;
        }
        RouteEdge evidence={0};
        unsigned timing=control ? move_timing(&machine,control) : 0;
        unsigned slot=timing>>8;
        const uint8_t *record=machine.board.ram+MOVE_LIST+16*(slot/3);
        unsigned outcome=record[2+((record[1]>>(2+2*(slot%3)))&3)];
        unsigned branch=move_branch(&machine);
        int video_start=machine.ldp.search_target;
        uint64_t shape=input_shape(&machine,false),mirror=input_shape(&machine,true);
        RouteEdge actual = {.timing=timing,.outcome=outcome};
        if(control) {
            Machine source=machine;connect_machine(&source);
            if(!terminal_proof) {
                /* Every selected action must reproduce its live progression
                 * evidence; final replay still requires a death-free ending. */
                ScoreBaseline baseline;score_baseline_init(&baseline,&source,graph);
                bool scores=false;
                phase=route_accepted_transition(&machine,graph,control,&actual,&baseline,&scores);
                if(!scores){fprintf(stderr,"Progression gate rejected replay step %u\n",i);fclose(file);return 3;}
            } else phase=route_transition(&machine,graph,control,&actual);
            if(terminal_proof) {
                if(actual.life_lost || !prove_terminal(&machine,&source,graph,&actual,phase==ROUTE_VICTORY)){fclose(file);return 3;}
                phase=ROUTE_VICTORY;
            }
        }
        else {
            RouteMonitor ending;monitor_start(&ending,&machine);
            bool won=false;
            while(machine.board.cycles<until && !ending.death) {
                won=won || offline_won(&machine.board,&machine.ldp);
                uint64_t next=machine.board.cycles+SLICE_CYCLES;if(next>until)next=until;
                monitored_run(&machine,next,&ending);
            }
            won=won || offline_won(&machine.board,&machine.ldp);route_monitor=NULL;
            DecisionKey ready;decision_key(&ready,&machine);
            phase=ending.death ? ROUTE_DEATH : won ? ROUTE_VICTORY : ready.count ? ROUTE_DECISION : ROUTE_UNRESOLVED;
            actual.press_cycle=press;actual.release_cycle=release;actual.until_cycle=machine.board.cycles;
            actual.life_lost=ending.death;
        }
        machine_key(&key, &machine, graph, phase);
        if (actual.life_lost || (control && !actual.seen) || phase == ROUTE_DEATH || phase == ROUTE_UNRESOLVED ||
            press != actual.press_cycle || release != actual.release_cycle || until != actual.until_cycle ||
            !hash_matches(to, key.a, key.b)) {
            fprintf(stderr, "Replay timing/target/death checkpoint mismatch at step %u\n", i); fclose(file); return 3;
        }
        if(control) {
            evidence=actual;
            printf("{\"type\":\"%s\",\"source_step\":%u,\"control\":%u,\"press_cycle\":%" PRIu64 ",\"release_cycle\":%" PRIu64 ",\"until_cycle\":%" PRIu64 ","
                   "\"frame\":%d,\"video_start\":%d,\"headers\":\"%016" PRIx64 "\",\"branch_state\":%u,\"input_seen\":%s,"
                   "\"score_before\":%d,\"score_after\":%d,\"no_input_after\":%d,\"timing\":%u,\"outcome\":%u,\"terminal_proof\":%s,\"progress_proof\":%s,"
                   "\"shape\":\"%016" PRIx64 "\",\"mirror_shape\":\"%016" PRIx64 "\",\"acceptance_evidence\":\"fresh ROM input-flags transition\"}\n",
                   "replay_move",i,control,actual.press_cycle,actual.release_cycle,actual.until_cycle,actual.frame,video_start,actual.headers,branch,actual.seen?"true":"false",
                   evidence.before,evidence.after,evidence.plain,actual.timing,actual.outcome,terminal_proof?"true":"false",actual.progress_proof?"true":"false",shape,mirror);
            fflush(stdout);
        }
        moves += control != 0;
    }
    if (fgetc(file) != EOF) { fprintf(stderr, "Trailing replay data\n"); fclose(file); return 3; }
    fclose(file);
    int score = 0;
    if (phase != ROUTE_VICTORY || !player_one_score(&machine.board, &score) || score != expected_score ||
        moves != expected_moves || !hash_matches(final_hash, key.a, key.b)) {
        fprintf(stderr, "Replay did not reproduce the requested victory score/move count\n"); return 3;
    }
    printf("{\"type\":\"replay\",\"verified\":true,\"terminal\":true,\"score\":%d,\"move_count\":%u,"
           "\"steps\":%u,\"root_hash\":\"%s\",\"final_hash\":\"%s\",\"lives\":%d}\n",
           score, moves, steps, root_hash, final_hash, player_one_lives(&machine.board));
    return 0;
}

/* Exercise the same compact lookup used in the APK, with its nominal
 * 30.5 Hz guidance polling, an 8 ms Android input poll and 100 ms holds.
 * A missing move is never replaced by the survival oracle during replay. */

/* One boot per graph, not per branch. Each case restores the exact verified
 * in-memory root and replays its input prefix; no external snapshot is read.
 * Length-prefixed UTF-8 paths preserve spaces without any shell parsing. */

#ifndef HYPCADE_SEARCH_NO_MAIN
int main(int argc, char **argv) {
    setvbuf(stdout,NULL,_IOLBF,0);
    RouteGraph graph={0};
    if(!parse_options(&graph.options,argc,argv) || !graph.options.replay) {
        fprintf(stderr,"usage: score-routes ROM GAME SKILL START_DELAY MAX_SECONDS --replay TRACE\n");return 2;
    }
    graph.nodes=calloc(1,sizeof *graph.nodes);
    if(!graph.nodes)return 1;
    int result=graph_boot(&graph) ? graph_replay(&graph) : 3;
    route_monitor=NULL;free(graph.nodes);return result;
}
#endif
