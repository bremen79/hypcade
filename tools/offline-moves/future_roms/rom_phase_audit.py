#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Observe instruction/refresh paths at a naturally reached ROM frontier.

Only a copied host Z80 gains an observation callback. ROM/RAM and production
sources stay unchanged. Three physical schedules diagnose the missing timing
relation; instruction samples alone do not prove universal reachability.
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
from future_roms import rom_timer_rules
from future_roms import rom_poll_rules
from future_roms import rom_sound_rules
from future_roms import rom_irq_rules
from future_roms import rom_irq_body_rules
from future_roms import rom_late_irq_rules

ROOT = CORE
PREFIX='''#include <stdbool.h>
static bool phase_frontier(void *,void *,void *,void *,int);
'''
SUFFIX=r'''
typedef struct {uint64_t visits,m1;unsigned deltas;} PhaseStat;
static PhaseStat ps[65537];
static Z80 *phase_active;
static unsigned phase_prev_pc,phase_prev_r,phase_target;
static bool phase_all_selector_sites;
static bool phase_have_prev,phase_found;
static unsigned phase_value,phase_at_pc;
static uint64_t phase_read_cycle,phase_instructions;
static unsigned phase_r_writes;
static unsigned phase_irq_pc,phase_irq_r,phase_irq_count;
static bool phase_in_irq;
typedef struct {uint8_t before[2],after[2];unsigned delta;uint64_t cycles;bool core;} PhasePrefix;
static PhasePrefix phase_prefixes[1024];
static bool phase_prefix_pending;
static uint8_t phase_sound_final[5],phase_filter_final[2];
static unsigned phase_core_entry,phase_prefix_r;
static uint64_t phase_prefix_cycle;
typedef struct {uint8_t before[0x210],after[0x210];unsigned iy,r,delta;} PhaseBody;
static PhaseBody phase_bodies[1024];
static unsigned phase_body_count;
static bool phase_body_pending;
static void phase_prefix_end(Z80 *z,bool core) {
    CineBoard *b=z->bus.ctx;PhasePrefix *p=&phase_prefixes[phase_irq_count];
    memcpy(p->after,b->ram+0x400,2);p->delta=(z->r-phase_prefix_r)&127;
    p->cycles=b->cycles-phase_prefix_cycle;p->core=core;phase_prefix_pending=false;
}
static unsigned phase_irq_delta[1024],phase_irq_flags[1024];
typedef struct {unsigned count,footer,after_footer,delta;uint8_t before[16][4],after[16][4];} PhaseTimer;
static PhaseTimer phase_timers[1024];
static unsigned phase_timer_entry,phase_timer_exit,phase_timer_count,phase_timer_r;
static bool phase_timer_pending;
typedef struct {unsigned m1,cycles;uint64_t count;} PhasePoll;
static PhasePoll phase_polls[128];
static unsigned phase_poll_count,phase_poll_entry,phase_poll_kind,phase_poll_r,phase_poll_m1,phase_poll_cycles;
static uint64_t phase_poll_cycle,phase_poll_instructions,phase_poll_start,phase_poll_interrupted;
static bool phase_poll_pending;
typedef struct {unsigned kind,delta,pc;int irq;uint8_t before[5],after[5];} PhaseSound;
typedef struct {bool active;unsigned r,sp,ret;int irq;uint8_t before[5];} PhaseSoundRun;
static PhaseSound phase_sounds[2048];
static PhaseSoundRun phase_sound_runs[2];
static unsigned phase_sound_count,phase_sound_entry,phase_sound_counter;
static uint8_t phase_sound_previous[5],phase_sound_initial[5];
static bool phase_sound_seen,phase_sound_inside;
static int phase_sound_previous_irq;
static void phase_sound_event(unsigned kind,const uint8_t *before,const uint8_t *after,unsigned delta,unsigned pc,int irq) {
    if(phase_sound_count>=2048){fprintf(stderr,"Sound observation capacity exceeded\n");exit(3);}
    PhaseSound *e=&phase_sounds[phase_sound_count++];e->kind=kind;e->delta=delta;e->pc=pc;e->irq=irq;
    memcpy(e->before,before,5);memcpy(e->after,after,5);
}
static void phase_sound_observe(Z80 *z,unsigned pc) {
    CineBoard *b=z->bus.ctx;const uint8_t *current=b->ram+0x1b;
    if(!phase_sound_seen) {memcpy(phase_sound_initial,current,5);phase_sound_seen=true;}
    else if(!phase_sound_inside && memcmp(phase_sound_previous,current,5))
        phase_sound_event(2,phase_sound_previous,current,0,phase_prev_pc,phase_sound_previous_irq);
    for(unsigned i=0;i<2;i++) {
        PhaseSoundRun *r=&phase_sound_runs[i];
        bool ended=i?(pc==r->ret && z->sp==r->sp+2):pc==phase_sound_counter+9;
        if(r->active && ended) {
            phase_sound_event(i,r->before,current,(z->r-r->r)&127,pc,r->irq);r->active=false;
        }
        if(pc==(i?phase_sound_entry:phase_sound_counter)) {
            if(r->active){fprintf(stderr,"Sound primitive reentry\n");exit(3);}
            if(i && (z->sp<0xa000 || z->sp>=0xa7ff)){fprintf(stderr,"Unexpected sound stack\n");exit(3);}
            r->active=true;r->r=z->r;r->sp=z->sp;r->irq=phase_in_irq?(int)phase_irq_count:-1;
            if(i)r->ret=b->ram[z->sp&0x7ff]|(b->ram[(z->sp+1)&0x7ff]<<8);
            memcpy(r->before,current,5);
        }
    }
    memcpy(phase_sound_previous,current,5);
}
static bool phase_released(const CineBoard *b) {
    const CineInputs *i=&b->inputs;
    return !(i->up || i->down || i->left || i->right || i->sword || i->cadet || i->captain || i->ace);
}
static bool phase_poll_cost(const Z80 *z,unsigned *m1,unsigned *cycles) {
    CineBoard *b=z->bus.ctx;
    if(!phase_released(b))return false;
    for(unsigned j=0;j<12;j++)if(b->ram[0x40+j]&224)return false;
    unsigned n=0,dm=0,dt=0;
    while(n<16 && (b->ram[0xe0+16*n]&128)) {
        const uint8_t *x=b->ram+0xe0+16*n;
        unsigned count=x[1]&3,active=4;
        if(!count || (x[0]&15)>10)return false;
        for(unsigned j=0;j<4;j++) {
            if(j>count && x[12+j])return false;
            if(active==4 && x[12+j])active=j;
        }
        if(!active){dm+=27;dt+=199;}
        else if(active==4){dm+=28+9*count;dt+=211+52*count;}
        else {dm+=30+9*active;dt+=245+52*active;}
        ++n;
    }
    unsigned at=0xe0+16*n,iy=((unsigned)z->iyh<<8)|z->iyl;
    if(iy!=0xa000+at || (b->ram[at]&192) || (b->ram[at+5]&64))return false;
    unsigned footer=b->ram[at+14]|(b->ram[at+15]<<8);
    if(!footer || (phase_poll_kind==1 && footer==b->ram[0x16]))return false;
    if(phase_poll_kind) {
        *m1=footer>=256?243:phase_poll_kind==1?247:248;
        *cycles=footer>=256?2031:phase_poll_kind==1?2073:2071;
    } else {
        *m1=footer>=256?245:248;*cycles=footer>=256?2051:2080;
        if(b->ram[at+5]&1){*m1+=6;*cycles+=62;}
    }
    *m1+=dm;*cycles+=dt;return true;
}
void phase_opcode(Z80 *z) {
    if(z!=phase_active || phase_found)return;
    unsigned pc=(z->nmi || (z->irq && z->iff1 && !z->ei_pending))?65536:z->pc;
    phase_sound_observe(z,pc);
    if(pc==phase_core_entry && phase_prefix_pending) {
        phase_prefix_end(z,true);
        if(phase_body_count>=1024 || phase_body_pending){fprintf(stderr,"IRQ body observation capacity\n");exit(3);}
        CineBoard *b=z->bus.ctx;PhaseBody *body=&phase_bodies[phase_body_count];
        memcpy(body->before,b->ram,sizeof body->before);body->iy=((unsigned)z->iyh<<8)|z->iyl;
        body->r=z->r;phase_body_pending=true;
    }
    if(pc==65536 && phase_poll_pending) {phase_poll_pending=false;++phase_poll_interrupted;}
    if(pc==phase_poll_entry) {
        CineBoard *b=z->bus.ctx;
        if(phase_poll_pending && phase_released(b)) {
            if(((z->r-phase_poll_r)&127)!=(phase_poll_m1&127) || b->cycles-phase_poll_cycle!=phase_poll_cycles) {
                fprintf(stderr,"Released-input poll transfer mismatch: R %u/%u cycles %" PRIu64 "/%u\n",
                    (z->r-phase_poll_r)&127,phase_poll_m1&127,b->cycles-phase_poll_cycle,phase_poll_cycles);exit(3);
            }
            unsigned j=0;while(j<phase_poll_count && (phase_polls[j].m1!=phase_poll_m1 || phase_polls[j].cycles!=phase_poll_cycles))++j;
            if(j==phase_poll_count) {
                if(j>=128){fprintf(stderr,"Poll group capacity exceeded\n");exit(3);}
                phase_polls[j]=(PhasePoll){phase_poll_m1,phase_poll_cycles,0};++phase_poll_count;
            }
            ++phase_polls[j].count;phase_poll_instructions+=phase_instructions-phase_poll_start;
        }
        phase_poll_pending=phase_poll_cost(z,&phase_poll_m1,&phase_poll_cycles);
        phase_poll_r=z->r;phase_poll_cycle=b->cycles;phase_poll_start=phase_instructions;
    }
    if(pc<0xa000) {
        CineBoard *b=z->bus.ctx;
        if(b->rom[pc]==0xed && b->rom[pc+1]==0x4f)++phase_r_writes;
    }
    if(pc==phase_timer_entry) {
        if(phase_timer_pending || phase_timer_count>=1024){fprintf(stderr,"Timer profile limit/reentry\n");exit(3);}
        CineBoard *b=z->bus.ctx;PhaseTimer *t=&phase_timers[phase_timer_count];t->count=0;
        while(t->count<16 && b->ram[0xe0+16*t->count]&128) {
            memcpy(t->before[t->count],b->ram+0xec+16*t->count,4);++t->count;
        }
        unsigned footer=((unsigned)z->iyh<<8)|z->iyl;
        if(footer!=0xa0e0+16*t->count){fprintf(stderr,"Unexpected timer footer\n");exit(3);}
        t->footer=b->ram[footer-0xa000+14]|(b->ram[footer-0xa000+15]<<8);
        phase_timer_r=z->r;phase_timer_pending=true;
    }
    if(pc==phase_timer_exit && phase_timer_pending) {
        CineBoard *b=z->bus.ctx;PhaseTimer *t=&phase_timers[phase_timer_count];
        for(unsigned i=0;i<t->count;i++)memcpy(t->after[i],b->ram+0xec+16*i,4);
        unsigned at=0xe0+16*t->count;
        t->after_footer=b->ram[at+14]|(b->ram[at+15]<<8);t->delta=(z->r-phase_timer_r)&127;
        ++phase_timer_count;phase_timer_pending=false;
    }
    if(phase_in_irq && pc==phase_irq_pc && z->iff1) {
        if(phase_irq_count>=1024){fprintf(stderr,"IRQ profile limit\n");exit(3);}
        if(phase_prefix_pending)phase_prefix_end(z,false);
        if(phase_body_pending) {
            CineBoard *b=z->bus.ctx;PhaseBody *body=&phase_bodies[phase_body_count++];
            memcpy(body->after,b->ram,sizeof body->after);body->delta=(z->r-body->r)&127;phase_body_pending=false;
        }
        phase_irq_delta[phase_irq_count++]=(z->r-phase_irq_r)&127;
        phase_in_irq=false;
    }
    if(pc==65536 && !phase_in_irq) {
        if(phase_irq_count>=1024){fprintf(stderr,"IRQ prefix capacity\n");exit(3);}
        phase_in_irq=true;phase_irq_pc=z->pc;phase_irq_r=z->r;
        CineBoard *b=z->bus.ctx;phase_irq_flags[phase_irq_count]=b->ram[8];
        memcpy(phase_prefixes[phase_irq_count].before,b->ram+0x400,2);
        phase_prefix_r=z->r;phase_prefix_cycle=b->cycles;phase_prefix_pending=true;
    }
    if(phase_have_prev) {
        unsigned delta=(z->r-phase_prev_r)&127;
        ps[phase_prev_pc].m1+=delta;ps[phase_prev_pc].deltas|=1U<<(delta&7);
    }
    if(pc==phase_target || (phase_all_selector_sites &&
            (pc==phase_target+14 || pc==phase_target+24 || pc==phase_target+34))) {
        phase_found=true;phase_value=(z->r+2)&127;phase_at_pc=z->pc;
        CineBoard *b=z->bus.ctx;phase_read_cycle=b->cycles;
        memcpy(phase_sound_final,b->ram+0x1b,5);memcpy(phase_filter_final,b->ram+0x400,2);return;
    }
    ++ps[pc].visits;++phase_instructions;
    phase_sound_inside=phase_sound_runs[0].active || phase_sound_runs[1].active;
    phase_sound_previous_irq=phase_in_irq?(int)phase_irq_count:-1;
    phase_prev_pc=pc;phase_prev_r=z->r;phase_have_prev=true;
}
static bool phase_frontier(void *source_ptr,void *trial_ptr,void *graph_ptr,void *edge_ptr,int old_phase) {
    Machine *source=source_ptr;RouteGraph *g=graph_ptr;RouteEdge *edge=edge_ptr;
    const char *target_scene=getenv("HYPCADE_PHASE_SCENE"),*target_step=getenv("HYPCADE_PHASE_STEP");
    unsigned scene=target_scene?(unsigned)strtoul(target_scene,NULL,0):53;
    unsigned step=target_step?(unsigned)strtoul(target_step,NULL,0):7;
    if((source->board.ram[14]&127)!=scene || source->board.ram[15]!=step)return true;
    phase_target=0;
    for(unsigned i=0;i+5<0xa000;i++)if(!memcmp(source->board.rom+i,"\xed\x5f\xe6\x07\xcb\x47",6)){phase_target=i;break;}
    if(!phase_target){fprintf(stderr,"Cannot locate mask-zero selector refresh read\n");exit(3);}
    const char *all_sites=getenv("HYPCADE_PHASE_ALL_SELECTOR_SITES");
    phase_all_selector_sites=all_sites && !strcmp(all_sites,"1");
    if(phase_all_selector_sites &&
        (memcmp(source->board.rom+phase_target+14,"\xed\x5f\xe6\x03\xfe\x03",6) ||
         memcmp(source->board.rom+phase_target+24,"\xed\x5f\xe6\x03\xfe\x03",6) ||
         memcmp(source->board.rom+phase_target+34,"\xed\x5f\xcb\x47",4))) {
        fprintf(stderr,"Unknown additional selector refresh sites\n");exit(3);
    }
    const char *timer_entry=getenv("HYPCADE_PHASE_TIMER_ENTRY"),*timer_exit=getenv("HYPCADE_PHASE_TIMER_EXIT");
    if(!timer_entry || !timer_exit)exit(3);
    phase_timer_entry=(unsigned)strtoul(timer_entry,NULL,10);phase_timer_exit=(unsigned)strtoul(timer_exit,NULL,10);
    const char *poll_entry=getenv("HYPCADE_PHASE_POLL_ENTRY"),*poll_kind=getenv("HYPCADE_PHASE_POLL_KIND");
    if(!poll_entry || !poll_kind)exit(3);
    phase_poll_entry=(unsigned)strtoul(poll_entry,NULL,10);phase_poll_kind=(unsigned)strtoul(poll_kind,NULL,10);
    const char *sound_entry=getenv("HYPCADE_PHASE_SOUND_ENTRY"),*sound_counter=getenv("HYPCADE_PHASE_SOUND_COUNTER");
    if(!sound_entry || !sound_counter)exit(3);
    phase_sound_entry=(unsigned)strtoul(sound_entry,NULL,10);phase_sound_counter=(unsigned)strtoul(sound_counter,NULL,10);
    const char *irq_core=getenv("HYPCADE_PHASE_IRQ_CORE");if(!irq_core)exit(3);
    phase_core_entry=(unsigned)strtoul(irq_core,NULL,10);
    static const unsigned delays[]={0,50,100};
    for(unsigned sample=0;sample<sizeof delays/sizeof *delays;sample++) {
        Machine candidate=*source;connect_machine(&candidate);
        memset(ps,0,sizeof ps);phase_have_prev=phase_found=phase_in_irq=phase_timer_pending=false;phase_instructions=0;
        phase_irq_count=phase_r_writes=phase_timer_count=0;
        phase_prefix_pending=false;
        phase_body_pending=false;phase_body_count=0;
        phase_poll_count=0;phase_poll_pending=false;phase_poll_instructions=phase_poll_interrupted=0;
        phase_sound_count=0;phase_sound_seen=phase_sound_inside=false;memset(phase_sound_runs,0,sizeof phase_sound_runs);
        phase_value=phase_at_pc=0;phase_read_cycle=0;phase_active=&candidate.board.cpu;
        unsigned initial_r=candidate.board.cpu.r;
        run_until(&candidate,candidate.board.cycles+(uint64_t)delays[sample]*(CINE_CPU_HZ/1000));
        ScoreBaseline baseline;score_baseline_init(&baseline,&candidate,g);
        RouteEdge actual={.timing=edge->timing,.outcome=edge->outcome};bool admitted=false;
        RoutePhase result=route_accepted_transition(&candidate,g,edge->control,&actual,&baseline,&admitted);
        RouteMonitor monitor;monitor_start(&monitor,&candidate);
        uint64_t end=candidate.board.cycles+20*(uint64_t)CINE_CPU_HZ;
        while(!phase_found && !monitor.death && candidate.board.cycles<end)
            monitored_run(&candidate,candidate.board.cycles+CINE_CPU_HZ/1000,&monitor);
        phase_active=NULL;route_monitor=NULL;
        printf("{\"type\":\"phase_path\",\"delay_ms\":%u,\"source_scene\":%u,\"source_step\":%u,\"source_cycle\":%" PRIu64 ",\"initial_r\":%u,\"accepted\":%s,\"life_lost\":%s,\"read_found\":%s,\"read_pc\":%u,\"read_r\":%u,\"read_cycle\":%" PRIu64 ",\"instructions\":%" PRIu64 ",\"stats\":[",
            delays[sample],scene,step,source->board.cycles,initial_r,admitted?"true":"false",actual.life_lost?"true":"false",
            phase_found?"true":"false",phase_at_pc,phase_value,phase_read_cycle,phase_instructions);
        bool comma=false;
        for(unsigned pc=0;pc<=65536;pc++)if(ps[pc].visits) {
            printf("%s[%u,%" PRIu64 ",%" PRIu64 ",%u]",comma?",":"",pc,ps[pc].visits,ps[pc].m1,ps[pc].deltas);comma=true;
        }
        printf("],\"r_writes\":%u,\"irqs\":[",phase_r_writes);
        for(unsigned i=0;i<phase_irq_count;i++)printf("%s[%u,%u]",i?",":"",phase_irq_delta[i],phase_irq_flags[i]);
        printf("],\"timer_updates\":[");
        for(unsigned i=0;i<phase_timer_count;i++) {
            PhaseTimer *t=&phase_timers[i];
            printf("%s{\"footer\":%u,\"after_footer\":%u,\"delta\":%u,\"before\":[",i?",":"",t->footer,t->after_footer,t->delta);
            for(unsigned j=0;j<t->count;j++)printf("%s[%u,%u,%u,%u]",j?",":"",t->before[j][0],t->before[j][1],t->before[j][2],t->before[j][3]);
            printf("],\"after\":[");
            for(unsigned j=0;j<t->count;j++)printf("%s[%u,%u,%u,%u]",j?",":"",t->after[j][0],t->after[j][1],t->after[j][2],t->after[j][3]);
            printf("]}");
        }
        printf("],\"poll_groups\":[");
        for(unsigned i=0;i<phase_poll_count;i++)printf("%s[%u,%u,%" PRIu64 "]",i?",":"",phase_polls[i].m1,phase_polls[i].cycles,phase_polls[i].count);
        printf("],\"poll_instructions\":%" PRIu64 ",\"poll_interruptions\":%" PRIu64,phase_poll_instructions,phase_poll_interrupted);
        printf(",\"source_pc\":%u,\"source_iff1\":%s,\"sound_initial\":[",source->board.cpu.pc,source->board.cpu.iff1?"true":"false");
        for(unsigned j=0;j<5;j++)printf("%s%u",j?",":"",phase_sound_initial[j]);
        printf("],\"sound_final\":[");
        for(unsigned j=0;j<5;j++)printf("%s%u",j?",":"",phase_sound_final[j]);
        printf("],\"sound_events\":[");
        for(unsigned i=0;i<phase_sound_count;i++) {
            PhaseSound *e=&phase_sounds[i];printf("%s{\"kind\":%u,\"delta\":%u,\"pc\":%u,\"irq\":%d,\"before\":[",i?",":"",e->kind,e->delta,e->pc,e->irq);
            for(unsigned j=0;j<5;j++)printf("%s%u",j?",":"",e->before[j]);
            printf("],\"after\":[");for(unsigned j=0;j<5;j++)printf("%s%u",j?",":"",e->after[j]);printf("]}");
        }
        printf("],\"irq_filter_initial\":[%u,%u],\"irq_filter_final\":[%u,%u],\"irq_prefixes\":[",
            source->board.ram[0x400],source->board.ram[0x401],phase_filter_final[0],phase_filter_final[1]);
        for(unsigned i=0;i<phase_irq_count;i++) {
            PhasePrefix *p=&phase_prefixes[i];
            printf("%s{\"before\":[%u,%u],\"after\":[%u,%u],\"delta\":%u,\"cycles\":%" PRIu64 ",\"core\":%s}",
                i?",":"",p->before[0],p->before[1],p->after[0],p->after[1],p->delta,p->cycles,p->core?"true":"false");
        }
        printf("],\"irq_bodies\":[");
        for(unsigned i=0;i<phase_body_count;i++) {
            PhaseBody *body=&phase_bodies[i];
            printf("%s{\"iy\":%u,\"delta\":%u,\"before\":\"",i?",":"",body->iy,body->delta);
            for(unsigned j=0;j<sizeof body->before;j++)printf("%02x",body->before[j]);
            printf("\",\"after\":\"");
            for(unsigned j=0;j<sizeof body->after;j++)printf("%02x",body->after[j]);
            printf("\"}");
        }
        puts("]}");
        fflush(stdout);(void)result;
    }
    (void)trial_ptr;(void)old_phase;exit(0);
}
'''


def build(output):
    output.mkdir(parents=True,exist_ok=True)
    player=(source_path('rom_routes.c')).read_text()
    needle='!rom_effective(&m,&trial,g,&edge,phase))'
    if player.count(needle)!=1:raise ValueError('ROM player admission changed')
    player=player.replace(needle,'!rom_effective(&m,&trial,g,&edge,phase) || !phase_frontier(&m,&trial,g,&edge,phase))')
    main=output/'phase-player.c';main.write_text(PREFIX+player+SUFFIX)
    vendor=ROOT/'vendor/src'
    core=(vendor/'cpu/z80.c').read_text()
    needle='int z80_step(Z80 *z)\n{'
    if core.count(needle)!=1:raise ValueError('Z80 entry changed')
    core=core.replace(needle,'extern void phase_opcode(Z80 *z);\n'+needle+'\n    phase_opcode(z);')
    observed_core=output/'observed-z80.c';observed_core.write_text(core)
    binary=output/'phase-player'
    moves.verify_vendor()
    subprocess.run([os.environ.get('CC','cc'),'-O3','-std=c11','-D_POSIX_C_SOURCE=200809L',
        '-Wall','-Wextra','-Werror','-I'+str(ROOT),'-I'+str(vendor),str(main),str(observed_core),
        *[str(vendor/p) for p in moves.SOURCES if p!='cpu/z80.c'],'-lz','-lm','-o',str(binary)],check=True)
    return binary.resolve()


def run(args):
    args.output.mkdir(parents=True,exist_ok=True)
    binary=build(args.output/'build')
    rom=rom_tables.load(args.rom,args.game)
    timer_bounds=rom_timer_rules.locate(rom);rom_timer_rules.validate_block(rom,timer_bounds)
    sound=rom_sound_rules.Rules(rom,args.game)
    irq=rom_irq_rules.Rules(rom,args.game)
    body_rule=(rom_irq_body_rules.Rules(rom,args.game) if args.game in rom_irq_body_rules.GAMES else
               rom_late_irq_rules.Rules(rom,args.game) if args.game in rom_late_irq_rules.GAMES else None)
    env=dict(os.environ,HYPCADE_PHASE_SCENE=str(args.scene),HYPCADE_PHASE_STEP=str(args.step),
             HYPCADE_PHASE_TIMER_ENTRY=str(timer_bounds[0]),HYPCADE_PHASE_TIMER_EXIT=str(timer_bounds[1]),
             HYPCADE_PHASE_POLL_ENTRY=str(rom_poll_rules.locate(rom)),
             HYPCADE_PHASE_POLL_KIND=str(1 if args.game=='ace' else 2 if args.game=='sae' else 0),
             HYPCADE_PHASE_SOUND_ENTRY=str(sound.entry),HYPCADE_PHASE_SOUND_COUNTER=str(sound.counter_entry),
             HYPCADE_PHASE_IRQ_CORE=str(irq.core_entry),
             HYPCADE_PHASE_ALL_SELECTOR_SITES='1' if args.all_selector_sites else '0')
    with (args.output/'profile.jsonl').open('w') as out,(args.output/'profile.log').open('w') as err:
        completed=subprocess.run([str(binary),str(args.rom.resolve()),args.game,'ace','0',str(args.policy.resolve()),
            str((args.output/'unused.trace').resolve()),'3600',str(args.difficulty)],env=env,stdout=out,stderr=err,timeout=60)
    rows=[r for r in rom_moves.records(args.output/'profile.jsonl') if r['type']=='phase_path']
    if completed.returncode!=0 or len(rows)!=3:raise ValueError('Incomplete original-ROM phase profiles')
    for row in rows:
        if not row['accepted'] or row['life_lost'] or not row['read_found']:
            raise ValueError('Physical schedule did not survive to the selector observation')
        if row['r_writes']:raise ValueError('Observed an R-register reset; net refresh deltas are not M1 counts')
        if row['read_found']:
            total=sum(s[2] for s in row['stats'])
            if (row['initial_r']+total+2)&127 != row['read_r']:
                raise ValueError('Observed instruction increments do not reconstruct the refresh read')
        timer_rule=rom_timer_rules.TimerRule(46,42,(-21,-14,-6,2),-3)
        for update in row['timer_updates']:
            after,footer,delta=timer_rule.delta(update['before'],update['footer'])
            if (after,footer,delta)!=(update['after'],update['after_footer'],update['delta']):
                raise ValueError('Timer potential differs during original whole-CPU/IRQ execution')
        def sound_state(values):
            d,f,low,high,c=values;return rom_sound_rules.State(f,low|(high<<8),d,c)
        initial=sound_state(row['sound_initial']);last=initial;total=jumps=counter_busy=sequence_busy=0
        counts=[0,0,0];full_irq=0
        for event in row['sound_events']:
            before=sound_state(event['before']);after=sound_state(event['after']);kind=event['kind'];counts[kind]+=1
            if before!=last:raise ValueError('Sound transfer observations are not contiguous')
            if kind==0:
                expected=rom_sound_rules.replace(before,counter=max(before.counter-1,0));delta=4+int(before.counter>0)
                counter_busy+=int(bool(before.flags&1) and before.counter>1)
            elif kind==1:
                expected,delta=sound.interpret(before);sequence_busy+=int(bool(before.flags&1) and before.counter>0)
            else:
                jumps+=sound.potential(after)-sound.potential(before);last=after;continue
            if (after,event['delta'])!=(expected,delta%128):raise ValueError('Sound primitive differs during physical IRQ execution')
            total+=event['delta']
            if event['irq']>=0:full_irq+=event['delta']
            last=after
        if last!=sound_state(row['sound_final']):raise ValueError('Final sound state is not accounted for')
        predicted=(4*(counts[0]+counts[1])+sound.potential(initial)-sound.potential(last)+jumps
                   -4*counter_busy+4*sequence_busy)%128
        if predicted!=total%128:raise ValueError('Interleaved sound potential does not reconstruct physical fetches')
        row['sound_summary']=dict(counter_calls=counts[0],sequence_calls=counts[1],outside_writes=counts[2],
            component_refresh=total%128,full_observed_irq_component_refresh=full_irq%128,predicted=predicted,
            potential_jumps=jumps%128,counter_busy=counter_busy,sequence_busy=sequence_busy)
        prefix_states=set();prefix_r=prefix_t=core_calls=0
        for event in row['irq_prefixes']:
            before=rom_irq_rules.State(*event['before']) if irq.filtered else rom_irq_rules.State()
            after=rom_irq_rules.State(*event['after']) if irq.filtered else before
            expected=irq.advance(before,1);prefix_states.add(before)
            if (after,int(event['core']),event['delta'],event['cycles'])!=(expected.state,expected.core_calls,expected.refresh,expected.cycles):
                raise ValueError('Original IRQ prefix differs from the finite entry rule')
            a=irq.core_potential(before);b=irq.core_potential(after)
            scale,weight_r,weight_t=(136,2140,20603) if irq.filtered else (1,3,33)
            if (scale*event['delta']-weight_r*int(event['core'])-a[0]+b[0])%(scale*128) or \
                    scale*event['cycles']!=weight_t*int(event['core'])+a[1]-b[1]:
                raise ValueError('Core-call potential differs from the original IRQ prefix')
            prefix_r+=event['delta'];prefix_t+=event['cycles'];core_calls+=event['core']
        if irq.filtered:
            bulk=irq.advance(rom_irq_rules.State(*row['irq_filter_initial']),len(row['irq_prefixes']))
            if (rom_irq_rules.State(*row['irq_filter_final']),core_calls,prefix_r%128,prefix_t)!=(bulk.state,bulk.core_calls,bulk.refresh,bulk.cycles):
                raise ValueError('IRQ filter bulk transfer differs from physical execution')
        row['irq_prefix_summary']=dict(native_states=len(prefix_states),accepted=len(row['irq_prefixes']),
            core_calls=core_calls,refresh=prefix_r%128,cycles=prefix_t,
            full_filter_period_covered=irq.filtered and len(prefix_states)==140)
        if body_rule is not None:
            body_r=0
            for event in row['irq_bodies']:
                before=bytearray.fromhex(event['before']);after=bytearray.fromhex(event['after'])
                expected,delta=body_rule.step(before+bytes(1024-len(before)),event['iy'])
                if expected[:len(after)]!=after or delta!=event['delta']:
                    raise ValueError('Normal IRQ body rule differs during physical gameplay')
                body_r+=delta
            if len(row['irq_bodies'])!=core_calls or (prefix_r+body_r)%128!=sum(e[0] for e in row['irqs'])%128:
                raise ValueError('Prefix and body summaries do not reconstruct all fully observed IRQs')
            row['irq_body_summary']=dict(native_calls=len(row['irq_bodies']),refresh=body_r%128,
                reconstructed_irq_refresh=(prefix_r+body_r)%128)
    report=dict(game=args.game,scene=args.scene,step=args.step,difficulty=args.difficulty,
                selector_observation='First read at any of the four mask-selector sites' if args.all_selector_sites else 'Mask-zero selector read',
                rows=rows,rom_sha256=hashlib.sha256(rom_tables.load(args.rom,args.game)).hexdigest(),
                sources={n:hashlib.sha256((source_path(n)).read_bytes()).hexdigest() for n in
                         ('rom_phase_audit.py','rom_timer_rules.py','rom_poll_rules.py','rom_sound_rules.py','rom_irq_rules.py','rom_irq_body_rules.py','rom_late_irq_rules.py','rom_routes.c','score_routes.c','score_trial.h')},
                z80_sha256=hashlib.sha256((source_path('vendor/src/cpu/z80.c')).read_bytes()).hexdigest(),
                scope='Three naturally reached physical schedules with instruction/R accounting, not an all-phase reachability proof')
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps([dict(delay_ms=r['delay_ms'],initial_r=r['initial_r'],read_r=r['read_r'],
        accepted=r['accepted'],instructions=r['instructions'],read_cycle=r['read_cycle']) for r in rows]))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',type=Path,required=True);p.add_argument('--game',choices=rom_tables.LAYOUTS,required=True)
    p.add_argument('--policy',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--scene',type=int,default=53);p.add_argument('--step',type=int,default=7)
    p.add_argument('--difficulty',type=int,default=0,choices=range(4))
    p.add_argument('--all-selector-sites',action='store_true',help='Stop at the first original selector read, including partially exhausted masks')
    run(p.parse_args())


if __name__=='__main__':main()
