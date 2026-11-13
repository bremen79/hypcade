/* SPDX-License-Identifier: GPL-3.0-or-later
 * Score evidence collected during the actual continuation. The shared no-input
 * copy starts from this expansion's exact state, not a move or scene recipe.
 * Store display changes only; memory does not grow with simulated frames.
 */
#define SCORE_BASELINE_EVENTS 2048

typedef struct {
    uint64_t cycle;
    int score;
    bool valid;
} ScoreEvent;

struct ScoreBaseline {
    Machine origin, plain;
    RouteGraph *graph;
    ScoreEvent events[SCORE_BASELINE_EVENTS];
    unsigned count;
    bool overflow;
};

typedef struct {
    Machine *machine;
    ScoreBaseline *baseline;
    RouteEdge *edge;
    int before;
    bool valid_start, proven;
} ScoreTrial;

static ScoreBaseline *baseline_writing;
static ScoreTrial *active_score_trial;

static void score_baseline_init(ScoreBaseline *b,const Machine *source,RouteGraph *graph) {
    b->origin=*source;connect_machine(&b->origin);
    b->plain=*source;connect_machine(&b->plain);
    b->graph=graph;b->count=1;b->overflow=false;
    b->events[0].cycle=source->board.cycles;
    b->events[0].score=0;
    b->events[0].valid=player_one_score(&source->board,&b->events[0].score);
}

static void score_baseline_write(void *ctx) {
    ScoreBaseline *b=baseline_writing;
    if(!b || ctx!=&b->plain.board || b->overflow)return;
    ScoreEvent event={.cycle=b->plain.board.cycles};
    event.valid=player_one_score(&b->plain.board,&event.score);
    const ScoreEvent *last=&b->events[b->count-1];
    if(event.valid==last->valid && event.score==last->score)return;
    if(b->count==SCORE_BASELINE_EVENTS){b->overflow=true;return;}
    b->events[b->count++]=event;
}

static bool score_baseline_at(ScoreBaseline *b,uint64_t cycle,int *score) {
    ++b->graph->baseline_queries;
    if(cycle<b->origin.board.cycles)return false;
    if(!b->overflow && b->plain.board.cycles<cycle) {
        ScoreBaseline *previous=baseline_writing;baseline_writing=b;
        uint64_t before=b->plain.board.cycles;
        /* Keep the released-input sweep's fixed slice schedule. A query in
         * the middle of a slice must not shift later player-update timing. */
        while(b->plain.board.cycles<cycle)
            run_until(&b->plain,b->plain.board.cycles+SLICE_CYCLES);
        b->graph->baseline_cycles+=b->plain.board.cycles-before;
        baseline_writing=previous;
    }
    if(b->overflow) {
        /* Unusual display activity cannot turn a memory limit into missing
         * evidence. Fall back to a fresh no-input execution for this query. */
        Machine plain=b->origin;connect_machine(&plain);
        uint64_t before=plain.board.cycles;
        run_until(&plain,cycle);
        b->graph->baseline_cycles+=plain.board.cycles-before;
        ++b->graph->baseline_fallbacks;
        return player_one_score(&plain.board,score);
    }
    /* A bus write belongs to the instruction beginning at event.cycle.
     * run_until(T) executes starts < T, including an instruction crossing T.
     * Keep the initial observation even when T equals the origin cycle. */
    unsigned low=1,high=b->count;
    while(low<high) {
        unsigned mid=low+(high-low)/2;
        if(b->events[mid].cycle<cycle)low=mid+1;else high=mid;
    }
    const ScoreEvent *event=&b->events[low-1];
    *score=event->score;return event->valid;
}

static void score_trial_observe(RouteMonitor *monitor) {
    ScoreTrial *p=active_score_trial;
    if(!p || p->machine!=monitor->machine)return;
    if(p->proven || !p->valid_start || monitor->death || !monitor->input_seen ||
       !monitor->score_valid ||
       monitor->machine->board.cycles-monitor->score_changed<SETTLE_CYCLES ||
       monitor->last_score<=p->before)return;
    int plain=0;
    if(score_baseline_at(p->baseline,monitor->machine->board.cycles,&plain) && monitor->last_score>plain) {
        p->edge->before=p->before;p->edge->after=monitor->last_score;p->edge->plain=plain;
        p->proven=true;
    }
}

/* Waiting is an explicit zero-cost choice. It cannot be silently replaced
 * by an unnecessary press merely because that press reaches a safe prompt. */


static RoutePhase route_accepted_transition(Machine *machine,RouteGraph *graph,unsigned control,
                                           RouteEdge *edge,ScoreBaseline *baseline,bool *accepted) {
    Machine source=*machine;
    ScoreTrial proof={.machine=machine,.baseline=baseline,.edge=edge};
    proof.valid_start=player_one_score(&machine->board,&proof.before);
    edge->before=proof.before;edge->progress_proof=edge->terminal_proof=false;
    ScoreTrial *previous=active_score_trial;active_score_trial=&proof;
    ++graph->fused_trials;
    RoutePhase phase=route_transition(machine,graph,control,edge);
    bool eligible=edge->seen && !edge->life_lost && (phase==ROUTE_DECISION || phase==ROUTE_VICTORY);
    if(eligible)++graph->score_probes;
    if(eligible && !proof.proven) {
        /* No award tail: the changed, stable playable prompt is the evidence.
         * Both that prompt and every subsequent action are checked again by
         * the complete replay before any move can be published. */
        edge->progress_proof=true;
        player_one_score(&machine->board,&edge->after);
        score_baseline_at(baseline,machine->board.cycles,&edge->plain);
        ++graph->progress_moves;
        if(phase==ROUTE_VICTORY)
            (void)prove_terminal(machine,&source,graph,edge,true);
    }
    active_score_trial=previous;route_monitor=NULL;
    *accepted=eligible && (proof.proven || edge->progress_proof);
    return phase;
}
