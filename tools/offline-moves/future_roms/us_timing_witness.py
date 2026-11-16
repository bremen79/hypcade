#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bind a US selector-support allocation with bounded physical timing probes.

A witness constructor, never a runtime fallback or an optimality proof by itself.
No ROM state is patched. Independent replay receives only the physical trace.
"""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import moves
import rom_moves
import rom_tables
import dl1_allocation
import cine_room_optimality
import rom_proof
import score_routes
import verify_cine_end

ROOT = CORE
PREFIX='''#include <stdbool.h>
static bool us_filter(void *,void *,void *,void *,int);
'''
SUFFIX=r'''
static unsigned us_group[39],us_root[39],us_moves[39],us_mask[39],us_current;
static bool us_loaded,us_invalid;
static Machine *us_future;
static unsigned us_next,us_loader;
static bool us_boundary,us_ready,us_wrong;
static unsigned us_seen_root,us_seen_mask;
static uint8_t (*us_original_read)(void *,uint16_t);
static uint8_t us_read(void *ctx,uint16_t address) {
    CineBoard *b=ctx;
    if(us_future && b==&us_future->board && address==us_loader && b->cpu.pc==(uint16_t)(address+1) &&
       b->ram[15]==0 && us_next<39 && (b->ram[0x36]&127)==us_group[us_next]) {
        us_boundary=true;
        us_seen_root=b->ram[14]&127;us_seen_mask=b->ram[0x60+us_group[us_next]]&7;
        if((b->ram[14]&127)!=us_root[us_next] || (b->ram[0x60+us_group[us_next]]&7)!=us_mask[us_next])us_wrong=true;
        if(us_moves[us_next])us_ready=true;
        ++us_next;
    }
    return us_original_read(ctx,address);
}
static int us_look(const Machine *trial,RouteGraph *g) {
    Machine future=*trial;connect_machine(&future);
    us_future=&future;us_next=us_current+1;us_boundary=us_ready=us_wrong=false;
    us_seen_root=us_seen_mask=255;
    /* The admitted transition may already have completed the next load. */
    if((future.board.ram[0x36]&127)!=us_group[us_current]) {
        unsigned ep=future.board.ram[0x36]&127;
        while(us_next<39 && us_group[us_next]!=ep && !us_moves[us_next]) {
            if((future.board.ram[0x60+us_group[us_next]]&7)!=us_mask[us_next]){us_future=NULL;return 2;}
            ++us_next;
        }
        us_seen_root=future.board.ram[14]&127;us_seen_mask=future.board.ram[0x60+ep]&7;
        if(us_next>=39 || us_group[us_next]!=ep || (future.board.ram[14]&127)!=us_root[us_next] ||
           (future.board.ram[0x60+ep]&7)!=us_mask[us_next]){us_future=NULL;return 2;}
        us_boundary=true;if(us_moves[us_next]){us_future=NULL;return 1;}++us_next;
    }
    us_original_read=future.board.cpu.bus.read;future.board.cpu.bus.read=us_read;
    RouteMonitor monitor;monitor_start(&monitor,&future);
    uint64_t end=future.board.cycles+30*(uint64_t)CINE_CPU_HZ;
    while(!us_ready && !us_wrong && !monitor.death && future.board.cycles<end && !offline_won(&future.board,&future.ldp))
        monitored_run(&future,future.board.cycles+CINE_CPU_HZ/1000,&monitor);
    us_future=NULL;route_monitor=NULL;(void)g;
    if(us_wrong)return 2;
    return us_boundary?1:0;
}
static bool us_filter(void *source_ptr,void *trial_ptr,void *graph_ptr,void *edge_ptr,int phase) {
    Machine *source=source_ptr,*trial=trial_ptr;RouteGraph *g=graph_ptr;RouteEdge *edge=edge_ptr;
    if(!us_loaded) {
        us_loaded=true;const char *path=getenv("HYPCADE_US_PLAN");FILE *f=path?fopen(path,"r"):NULL;
        if(!f){us_invalid=true;return false;}
        for(unsigned i=0;i<39;i++)if(fscanf(f,"%u %u %u %u",us_group+i,us_root+i,us_moves+i,us_mask+i)!=4)us_invalid=true;
        fclose(f);us_loader=(!strcmp(g->options.game,"lair_e"))?0x1547:(!strcmp(g->options.game,"lair_f"))?0x15b4:0x2403;
        if((source->board.ram[0x36]&127)!=us_group[0] || (source->board.ram[14]&127)!=us_root[0]) {
            fprintf(stderr,"US initial root differs from the allocation; condition it on the loaded variant\n");
            us_invalid=true;
        }
    }
    if(us_invalid)return false;
    unsigned ep=source->board.ram[0x36]&127,scene=source->board.ram[14]&127;
    while(us_current<39 && (us_group[us_current]!=ep || us_root[us_current]!=scene))++us_current;
    if(us_current>=39){fprintf(stderr,"US plan source mismatch ep=%u scene=%u\n",ep,scene);us_invalid=true;return false;}
    if(us_current==38)return true;
    int look=us_look(trial,g);
    if(look!=2)return true; /* More inputs needed, or the suffix already matches. */
    uint64_t seen[2]={0,0};
    for(unsigned attempt=0;attempt<256;attempt++) {
        Machine candidate=*source;connect_machine(&candidate);
        uint64_t delay=attempt<128?(uint64_t)attempt*256:(uint64_t)(attempt-128)*(CINE_CPU_HZ/1000);
        run_until(&candidate,candidate.board.cycles+delay);
        ScoreBaseline baseline;score_baseline_init(&baseline,&candidate,g);
        RouteEdge replacement={.timing=edge->timing,.outcome=edge->outcome};bool admitted=false;
        RoutePhase result=route_accepted_transition(&candidate,g,edge->control,&replacement,&baseline,&admitted);
        if(!admitted || !replacement.seen || replacement.life_lost || result!=(RoutePhase)phase)continue;
        if(!rom_effective(source,&candidate,g,&replacement,result))continue;
        int observed=us_look(&candidate,g);
        if(us_seen_root<128)seen[us_seen_root/64]|=UINT64_C(1)<<(us_seen_root%64);
        if(observed!=1)continue;
        printf("{\"type\":\"us_timing_probe\",\"visit\":%u,\"scene\":%u,\"step\":%u,\"delay_cycles\":%u}\n",
               us_current,scene,source->board.ram[15],(unsigned)delay);
        *trial=candidate;connect_machine(trial);*edge=replacement;return true;
    }
    /* The short offsets above need not reach the whole accepted window.
     * Sweep the released original execution deterministically, trying the
     * same descriptor window throughout its actual lifetime. A failed sweep
     * remains inconclusive; an admitted physical trace is the evidence. */
    if(edge->control) {
        Machine released=*source;connect_machine(&released);
        RouteMonitor waiting;monitor_start(&waiting,&released);unsigned probes=0;
        uint64_t end=source->board.cycles+40*(uint64_t)CINE_CPU_HZ;
        while(released.board.cycles<end && !waiting.death && probes<2048 &&
              (released.board.ram[14]&127)==scene && released.board.ram[15]==source->board.ram[15]) {
            unsigned timing=move_timing(&released,edge->control);
            if(timing && (timing>>8)==(edge->timing>>8) && released.ldp.state==LDP_PLAYING) {
                ++probes;Machine candidate=*source;connect_machine(&candidate);
                run_until(&candidate,released.board.cycles);
                ScoreBaseline baseline;score_baseline_init(&baseline,&candidate,g);
                RouteEdge replacement={.timing=move_timing(&candidate,edge->control),.outcome=edge->outcome};bool admitted=false;
                RoutePhase result=route_accepted_transition(&candidate,g,edge->control,&replacement,&baseline,&admitted);
                if(admitted && replacement.seen && !replacement.life_lost && result==(RoutePhase)phase &&
                   rom_effective(source,&candidate,g,&replacement,result)) {
                    int observed=us_look(&candidate,g);
                    if(us_seen_root<128)seen[us_seen_root/64]|=UINT64_C(1)<<(us_seen_root%64);
                    if(observed==1) {
                        printf("{\"type\":\"us_window_probe\",\"visit\":%u,\"scene\":%u,\"step\":%u,\"delay_cycles\":%" PRIu64 ",\"probes\":%u}\n",
                            us_current,scene,source->board.ram[15],replacement.press_cycle-source->board.cycles,probes);
                        *trial=candidate;connect_machine(trial);*edge=replacement;return true;
                    }
                }
            }
            route_monitor=&waiting;
            /* Hardware IRQs are 131072 cycles apart, not 60 Hz. A 61-tick
             * window spans about two seconds; a 1024 x 1ms cap misses its
             * late 39..61-tick polling regime. Spread bounded probes over
             * the entire window rather than exhausting them at its start. */
            monitored_run(&released,released.board.cycles+CINE_CPU_HZ/125+13*(probes%17),&waiting);
        }
        route_monitor=NULL;
    }
    fprintf(stderr,"US timing frontier failed visit=%u scene=%u step=%u expected=%u observed=%" PRIx64 ":%" PRIx64 "\n",
            us_current,scene,source->board.ram[15],us_root[us_current+1],seen[1],seen[0]);
    us_invalid=true; /* Analyze this frontier before repeating physical probes. */
    return false;
}
'''


def build(output):
    output.mkdir(parents=True,exist_ok=True)
    source=(source_path('rom_routes.c')).read_text()
    needle='!rom_effective(&m,&trial,g,&edge,phase))'
    if source.count(needle)!=1:raise ValueError('ROM player trial admission changed')
    source=source.replace(needle,'!rom_effective(&m,&trial,g,&edge,phase) || !us_filter(&m,&trial,g,&edge,phase))')
    staged=output/'us-witness.c';staged.write_text(PREFIX+source+SUFFIX)
    binary=output/'us-witness';vendor=ROOT/'vendor/src'
    moves.verify_vendor()
    subprocess.run([os.environ.get('CC','cc'),'-O3','-std=c11','-D_POSIX_C_SOURCE=200809L',
        '-Wall','-Wextra','-Werror','-I'+str(ROOT),'-I'+str(vendor),str(staged),
        *[str(vendor/p) for p in moves.SOURCES],'-lz','-lm','-o',str(binary)],check=True)
    return binary.resolve()


def run(args):
    args.output.mkdir(parents=True,exist_ok=True)
    report=json.loads(args.allocation.read_text())
    game=next(r for r in report['cases'] if r['game']==args.game)
    row=next(r for r in game['results'] if r['objective']==args.objective and r['difficulty']==args.difficulty)
    rom=rom_tables.load(args.rom,args.game)
    model=cine_room_optimality.Model(rom,args.game);graph=model.graph();values=rom_proof.solve(graph)
    room_costs=dl1_allocation.costs(model,graph,values,args.objective)
    offset=42 if args.game in ('lair_e','lair_f') else 40
    lines=[]
    for lap in range(3):
        for group in range(1,14):
            if group==13:root=row['final_group'][lap]+offset;mask=(4,6,7)[lap]
            else:
                part=row['allocation']['groups'][group-1];root=part['roots'][lap]
                mask=part['mask_after_'+('first','second','third')[lap]]
            pair=room_costs[root];commands=pair[0] if args.objective=='shortest' else pair[1]
            lines.append('%d %d %d %d'%(group,root,commands,mask))
    plan=args.output/'plan.txt';plan.write_text('\n'.join(lines)+'\n')
    binary=build(args.output/'build')
    trace=args.output/'route.trace';env=dict(os.environ,HYPCADE_US_PLAN=str(plan.resolve()))
    policy=args.policies/args.game/(args.objective+'.policy')
    timed_out=False
    with (args.output/'play.jsonl').open('w') as out,(args.output/'play.log').open('w') as err:
        try:
            played=subprocess.run([str(binary),str(args.rom.resolve()),args.game,'ace',str(args.start_delay),str(policy.resolve()),
                str(trace.resolve()),'3600',str(args.difficulty)],env=env,stdout=out,stderr=err,timeout=120)
        except subprocess.TimeoutExpired:
            timed_out=True
            played=subprocess.CompletedProcess([],124)
    play=next((r for r in rom_moves.records(args.output/'play.jsonl') if r['type']=='rom_play'),{})
    replay={};rom_end={};code=None
    if played.returncode==0:
        verifier=verify_cine_end.build(args.output/'replay-build')
        end_pc,end_frames=verify_cine_end.metadata(rom,args.game)
        with (args.output/'replay.jsonl').open('w') as out,(args.output/'replay.log').open('w') as err:
            checked=subprocess.run([str(verifier),str(args.rom.resolve()),args.game,'ace',str(args.start_delay),'3600',
                '--difficulty',str(args.difficulty),'--replay',str(trace.resolve())],stdout=out,stderr=err,timeout=120,
                env=dict(os.environ,HYPCADE_END_PC=str(end_pc),HYPCADE_END_FRAME0=str(end_frames[0]),HYPCADE_END_FRAME1=str(end_frames[1])))
        replay=next((r for r in rom_moves.records(args.output/'replay.jsonl') if r['type']=='replay'),{})
        rom_end=next((r for r in rom_moves.records(args.output/'replay.jsonl') if r['type']=='rom_end'),{})
        code=checked.returncode
    result=dict(game=args.game,objective=args.objective,difficulty=args.difficulty,start_delay=args.start_delay,
        support_bound=[row['inputs'],row['score']],play=play,replay=replay,rom_end=rom_end,timed_out=timed_out,
        attained=bool(played.returncode==0 and code==0 and replay.get('verified') and
                      rom_end.get('verified') and
                      (replay.get('move_count')==row['inputs'] if args.objective=='shortest' else replay.get('score')==row['score'])),
        both_components_attained=bool(replay.get('verified') and
                      [replay.get('move_count'),replay.get('score')]==[row['inputs'],row['score']]),
        generated_c_sha256=hashlib.sha256((args.output/'build/us-witness.c').read_bytes()).hexdigest(),
        allocation_sha256=hashlib.sha256(args.allocation.read_bytes()).hexdigest(),
        scope='Bounded physical timing witness for one initial state; not a runtime selector or exhaustive phase proof')
    (args.output/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',type=Path,required=True);p.add_argument('--game',required=True,choices=cine_room_optimality.GAMES[1:])
    p.add_argument('--allocation',type=Path,required=True);p.add_argument('--policies',type=Path,required=True)
    p.add_argument('--objective',choices=('shortest','highest-score'),required=True)
    p.add_argument('--difficulty',type=int,choices=range(4),default=0);p.add_argument('--start-delay',type=float,default=0)
    p.add_argument('--output',type=Path,required=True)
    run(p.parse_args())


if __name__=='__main__':main()
