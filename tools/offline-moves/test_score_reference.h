/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later
 * Independent slow reference used only by synthetic regression tests.
 */
/* A fresh acknowledgment and a settled P1 increase against a simultaneous
 * released-input copy are both mandatory. Delayed awards are allowed, but a
 * death before the award rejects it. Full route replay checks later deaths. */
static bool route_score_reference(const Machine *base, unsigned control, RouteEdge *edge) {
    Machine trial=*base,plain=*base;connect_machine(&trial);connect_machine(&plain);
    RouteMonitor monitor;monitor_start(&monitor,&trial);
    int before=0;if(!player_one_score(&base->board,&before)){route_monitor=NULL;return false;}
    int input=control==16?0:(int)control;
    monitor.watched_input=input;
    monitor.input_last=trial.board.ram[INPUT_FLAGS+monitor.watched_input];
    monitor.input_armed=!(monitor.input_last&INPUT_SEEN);
    set_input(&trial.board.inputs,input,true);
    uint64_t release=trial.board.cycles+400000,end=release+10*(uint64_t)CINE_CPU_HZ;
    while(trial.board.cycles<end && !monitor.death) {
        if(trial.board.cycles>=release)set_input(&trial.board.inputs,input,false);
        route_monitor=&monitor;monitored_run(&trial,trial.board.cycles+SLICE_CYCLES,&monitor);
        route_monitor=NULL;run_until(&plain,trial.board.cycles);
        if(monitor.death)break;
        int baseline=0;
        if(monitor.input_seen && monitor.score_valid && trial.board.cycles-monitor.score_changed>=SETTLE_CYCLES &&
           player_one_score(&plain.board,&baseline) && monitor.last_score>before && monitor.last_score>baseline) {
            edge->before=before;edge->after=monitor.last_score;edge->plain=baseline;return true;
        }
        if(trial.board.cycles>=release && !monitor.input_seen)break;
    }
    edge->before=before;edge->after=monitor.last_score;
    player_one_score(&plain.board,&edge->plain);
    edge->seen=monitor.input_seen;edge->life_lost=monitor.death;
    route_monitor=NULL;return false;
}

