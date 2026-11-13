#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""No commercial ROMs: delayed rewards, transient deaths and policy timing."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import moves as move_tools

class ScoreRoutesTest(unittest.TestCase):
    def test_native_delayed_score_life_loss_and_timing(self):
        program=r'''
#define HYPCADE_SEARCH_NO_MAIN
#include "score_routes.c"
#include "test_score_reference.h"
#include <assert.h>
#include <unistd.h>
static void setup(Machine *m) {
    memset(m,0,sizeof *m);ldp_init(&m->ldp,24000.0/1001.0,1000);
    ldv1000_init(&m->player,&m->ldp,CINE_CPU_HZ);
    cine_reset(&m->board,cine_ldv1000_link(&m->player));
    original_board_write=m->board.cpu.bus.write;m->board.cpu.bus.write=monitored_board_write;
    memset(m->board.digits,0,sizeof m->board.digits);m->board.digits[6]=5;ldp_play(&m->ldp);
    m->board.ram[MOVE_LIST]=0x81;m->board.ram[MOVE_LIST+1]=1;
    m->board.ram[MOVE_LIST+2]=3;m->board.ram[MOVE_LIST+13]=255;
}
int main(void) {
    RouteOptions options;
    char *args[]={"test","rom.zip","ace","ace","0","3600","--replay","trace"};
    assert(parse_options(&options,8,args) && options.replay);
    args[6]="--policy";assert(!parse_options(&options,8,args));
    args[6]="--replay";args[4]="nan";assert(!parse_options(&options,8,args));
    char *settings[]={"test","rom.zip","ace","captain","0","3600","--difficulty","3","--replay","trace"};
    assert(parse_options(&options,10,settings) && options.difficulty==3 && options.replay);
    settings[7]="4";assert(!parse_options(&options,10,settings));
    settings[7]="3";settings[2]="dle21";settings[3]="ace";
    assert(!parse_options(&options,10,settings));
    settings[7]="0";assert(parse_options(&options,10,settings));
    settings[8]="--difficulty";settings[9]="0";assert(!parse_options(&options,10,settings));
    Machine m;setup(&m);
    const uint8_t delayed[]={0x3a,0x08,0xc0,0xe6,0x01,0x20,0xf9,
        0xaf,0x32,0x41,0xa0,0x3e,0x40,0x32,0x41,0xa0,
        0x16,0x14,0x01,0xff,0xff,0x0b,0x78,0xb1,0x20,0xfb,
        0x15,0x20,0xf5,0x3e,0x07,0x32,0x3d,0xe0,0xc3,0x22,0x00};
    memcpy(m.board.rom,delayed,sizeof delayed);RouteEdge evidence={0};
    assert(route_score_reference(&m,1,&evidence));
    assert(evidence.before==0 && evidence.after==7 && evidence.plain==0);
    assert(m.board.cycles==0 && m.board.digits[5]==0);
    /* Ignored presses stop at release, without seeking another decision.
     * Sticky flags from a previous press do not count as acknowledgment. */
    RouteGraph early={0};early.deadline=40*(uint64_t)CINE_CPU_HZ;
    for (unsigned stale=0;stale<2;stale++) {
        setup(&m);m.board.rom[0]=0xc3;
        m.board.ram[INPUT_FLAGS+1]=stale ? INPUT_SEEN : 0;
        RouteEdge ignored={0};
        assert(route_transition(&m,&early,1,&ignored)==ROUTE_IGNORED);
        assert(!ignored.seen && !ignored.life_lost && !m.board.inputs.up);
        assert(ignored.release_cycle>=400000 && ignored.release_cycle<400032);
        assert(ignored.until_cycle==ignored.release_cycle && route_monitor==NULL);
    }
    assert(early.ignored_early_exits==2 && !early.time_cap && !early.transition_cap);
    /* An acknowledgment near the end of the hold still gets its normal
     * continuation, even though the input was ignored for most of the hold. */
    setup(&m);
    const uint8_t late[]={0x01,0x00,0x38,0x0b,0x78,0xb1,0x20,0xfb,
        0xaf,0x32,0x41,0xa0,0x3e,0x40,0x32,0x41,0xa0,
        0x3e,0x82,0x32,0xe0,0xa0,0xc3,22,0};
    memcpy(m.board.rom,late,sizeof late);RouteEdge accepted={0};
    assert(route_transition(&m,&early,1,&accepted)==ROUTE_DECISION);
    assert(accepted.seen && !accepted.life_lost && !m.board.inputs.up);
    assert(accepted.until_cycle>accepted.release_cycle && early.ignored_early_exits==2);
    /* Score history supports out-of-order candidate times without replaying
     * the no-input CPU. Instruction-boundary queries match fresh executions. */
    setup(&m);
    const uint8_t changes[]={0x3e,1,0x32,0x3d,0xe0,0x3e,2,0x32,0x3d,0xe0,
        0x3e,3,0x32,0x3d,0xe0,0xc3,15,0};
    memcpy(m.board.rom,changes,sizeof changes);
    RouteGraph causal={0};causal.deadline=40*(uint64_t)CINE_CPU_HZ;
    ScoreBaseline baseline;score_baseline_init(&baseline,&m,&causal);
    const uint64_t queries[]={200,1,7,8,20,27,28,47,48,60,0};
    for(unsigned i=0;i<sizeof queries/sizeof *queries;i++) {
        Machine reference=m;connect_machine(&reference);run_until(&reference,queries[i]);
        int expected=0,actual_score=0;
        bool valid=player_one_score(&reference.board,&expected);
        assert(score_baseline_at(&baseline,queries[i],&actual_score)==valid && actual_score==expected);
    }
    assert(baseline.count==4 && causal.baseline_cycles<SLICE_CYCLES+32 && !causal.baseline_fallbacks);
    baseline.count=SCORE_BASELINE_EVENTS;
    baseline.events[SCORE_BASELINE_EVENTS-1]=(ScoreEvent){.score=999,.valid=true};
    baseline_writing=&baseline;score_baseline_write(&baseline.plain.board);baseline_writing=NULL;
    int actual_score=0;
    assert(baseline.overflow && score_baseline_at(&baseline,48,&actual_score) && actual_score==3);
    assert(causal.baseline_fallbacks==1);
    /* A new playable prompt ends the trial immediately. A later award is
     * no longer needed, and the exact decision checkpoint is unchanged. */
    setup(&m);
    const uint8_t delayed_after_prompt[]={0x3a,0x08,0xc0,0xe6,1,0x20,0xf9,
        0xaf,0x32,0x41,0xa0,0x3e,0x40,0x32,0x41,0xa0,
        0x3e,0x82,0x32,0xe0,0xa0,
        0x01,0xff,0xff,0x0b,0x78,0xb1,0x20,0xfb,
        0x3e,7,0x32,0x3d,0xe0,0xc3,34,0};
    memcpy(m.board.rom,delayed_after_prompt,sizeof delayed_after_prompt);
    Machine fused=m,reference=m;connect_machine(&fused);connect_machine(&reference);
    RouteEdge original={0},combined={0},counterfactual={0};
    assert(route_transition(&reference,&causal,1,&original)==ROUTE_DECISION);
    assert(route_score_reference(&m,1,&counterfactual) && counterfactual.after==7);
    score_baseline_init(&baseline,&m,&causal);bool scores=false;
    assert(route_accepted_transition(&fused,&causal,1,&combined,&baseline,&scores)==ROUTE_DECISION);
    assert(scores && combined.progress_proof && combined.after==0 && combined.plain==0);
    assert(fused.board.cycles==reference.board.cycles && fused.board.digits[5]==0);
    StateKey fused_key,reference_key;machine_key(&fused_key,&fused,&causal,ROUTE_DECISION);
    machine_key(&reference_key,&reference,&causal,ROUTE_DECISION);
    assert(fused_key.used==reference_key.used && !memcmp(fused_key.bytes,reference_key.bytes,fused_key.used));
    assert(active_score_trial==NULL && route_monitor==NULL);
    /* Deadline truncation is unresolved, never a completed ignored trial. */
    setup(&m);m.board.rom[0]=0xc3;early.deadline=200000;RouteEdge truncated={0};
    assert(route_transition(&m,&early,1,&truncated)==ROUTE_UNRESOLVED);
    assert(early.time_cap && early.ignored_early_exits==2 && !m.board.inputs.up);
    setup(&m);const uint8_t death[]={0x3e,4,0x32,0x3e,0xe0,0x3e,5,0x32,0x3e,0xe0,0xc3,10,0};
    memcpy(m.board.rom,death,sizeof death);RouteMonitor monitor;monitor_start(&monitor,&m);
    monitored_run(&m,SLICE_CYCLES,&monitor);route_monitor=NULL;
    assert(monitor.death && m.board.digits[6]==5);
    setup(&m);memcpy(m.board.rom,death,sizeof death);
    early.deadline=40*(uint64_t)CINE_CPU_HZ;RouteEdge fatal={0};
    assert(route_transition(&m,&early,1,&fatal)==ROUTE_DEATH);
    assert(fatal.life_lost && !m.board.inputs.up && early.ignored_early_exits==2);
    setup(&m);memcpy(m.board.rom,death,sizeof death);score_baseline_init(&baseline,&m,&causal);


    setup(&m);m.ldp.frame=31070;
    const uint8_t rescue[]={0x3a,0x08,0xc0,0xe6,1,0x28,8,
        0x3e,4,0x32,0x3e,0xe0,0xc3,12,0,
        0xaf,0x32,0x41,0xa0,0x3e,0x40,0x32,0x41,0xa0,0xc3,24,0};
    memcpy(m.board.rom,rescue,sizeof rescue);
    Machine rescued=m;connect_machine(&rescued);set_input(&rescued.board.inputs,1,true);
    run_until(&rescued,400000);set_input(&rescued.board.inputs,1,false);
    RouteGraph g={0};g.deadline=40*(uint64_t)CINE_CPU_HZ;
    RouteEdge required={.control=1,.seen=true};
    assert(prove_terminal(&rescued,&m,&g,&required,false));
    assert(required.terminal_proof && required.before==required.after && (required.timing&0x4000));
    rescued=m;connect_machine(&rescued);ScoreBaseline ending_baseline;
    score_baseline_init(&ending_baseline,&m,&g);bool accepted_ending=false;RouteEdge ending_edge={0};
    assert(route_accepted_transition(&rescued,&g,1,&ending_edge,&ending_baseline,&accepted_ending)==ROUTE_VICTORY);
    assert(accepted_ending && ending_edge.terminal_proof && ending_edge.progress_proof && ending_edge.before==ending_edge.after);

    setup(&m);m.ldp.frame=31070;m.board.rom[0]=0xc3;m.board.rom[1]=m.board.rom[2]=0;
    rescued=m;connect_machine(&rescued);run_until(&rescued,400000);
    assert(!prove_terminal(&rescued,&m,&g,&required,false)); /* optional input must be rejected */
    setup(&m);m.board.ram[MOVE_LIST]=0x84;m.board.ram[MOVE_LIST+2]=3;
    Machine mirrored=m;connect_machine(&mirrored);mirrored.board.ram[MOVE_LIST]=0x88;
    assert(input_shape(&m,false)==input_shape(&mirrored,true));
    assert(headers_hash(&m.board)!=headers_hash(&mirrored.board));
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            tmp=Path(directory);(tmp/'test.c').write_text(program);src=move_tools.ROOT/'vendor/src'
            subprocess.run(['cc','-O2','-std=c11','-D_POSIX_C_SOURCE=200809L','-Wall','-Wextra','-Werror',
                            '-I'+str(move_tools.ROOT),'-I'+str(src),str(tmp/'test.c'),
                            *[str(src/p) for p in move_tools.SOURCES],'-lz','-lm','-o',str(tmp/'test')],check=True)
            subprocess.run([str(tmp/'test')],check=True)

if __name__=='__main__':unittest.main()
