/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later
 * Exercise the packaged move sets with Android's IRQ guidance cadence,
 * 8 ms controller polling, SDL's 17 ms input queue and 100 ms presses. Original CPU/player, no media. */
#define HYPCADE_SEARCH_NO_MAIN
#define HYPCADE_ROM_ROUTES_NO_MAIN
#include "rom_routes.c"
#ifndef HYPCADE_MOVES_INCLUDE
#define HYPCADE_MOVES_INCLUDE "../../android/app/jni/arcade_moves.inc"
#endif
#include "../../android/app/jni/arcade_move_catalog.h"
#include HYPCADE_MOVES_INCLUDE
int main(int argc,char **argv) {
    if(argc<9 || argc>11)return 2;
    (void)play_tables;
    (void)read_choices;
    char *base[]={argv[0],argv[1],argv[2],argv[3],argv[4],argv[5],"--difficulty",argv[7]};
    RouteGraph g={0};if(!parse_options(&g.options,8,base))return 2;
    uint64_t mode_value;if(!parse_unsigned(argv[6],2,&mode_value))return 2;
    unsigned mode=(unsigned)mode_value;
    uint64_t detour_target=0;
    if(argc>=10 && !parse_unsigned(argv[9],1000,&detour_target))return 2;
    uint64_t miss_target=0;
    if(argc==11 && !parse_unsigned(argv[10],1000,&miss_target))return 2;
    uint64_t phase_value;if(!parse_unsigned(argv[8],16,&phase_value))return 2;
    uint64_t phase_cycles=phase_value*4000;
    g.nodes=calloc(1,sizeof *g.nodes);
    if(!g.nodes)return 1;
    if(!graph_boot(&g))return 3;
    Machine m=g.base;connect_machine(&m);bool ace=m.board.game==CINE_SPACE_ACE;
    const ArcadeCineProfile *policy=arcade_cine_profile(arcade_cine_profiles,
        ARCADE_COUNT(arcade_cine_profiles),g.options.game);
    if(!policy)return 2;
    unsigned strategy=mode==2, other_strategy=!strategy;
    unsigned detour_seen=0;uint32_t detour_state=UINT32_MAX,last_difference=UINT32_MAX;
    bool detour_applied=false;
    uint64_t poll=((m.board.cycles+31999)/32000)*32000,guide=m.board.next_irq,release=0,previous=0;
    uint64_t input_at=((m.board.cycles+phase_cycles+67999)/68000)*68000-phase_cycles;
    struct {unsigned control;bool down;} queue[16];unsigned queued=0;
    unsigned held=0,pending=0,moves_count=0,losses=0;bool was_ready=false,missed=false,suppress=false;
    ArcadeMoveSelection selected={0,false,0};
    RouteMonitor live;monitor_start(&live,&m);uint32_t last_unknown=UINT32_MAX;
    while(m.board.cycles<g.deadline) {
        if(live.death) {
            ++losses;
            fprintf(stderr,"life lost=%u scene=%u step=%u frame=%d lives=%d\n",losses,m.board.ram[14]&127,m.board.ram[15]&127,m.ldp.frame,player_one_lives(&m.board));
            if(!missed || losses>1 || player_one_lives(&m.board)<=0)break;
            if(held)set_input(&m.board.inputs,held==16?0:(int)held,false);
            held=pending=queued=0;was_ready=false;previous=0;suppress=false;
            monitor_start(&live,&m);
        }
        if(offline_won(&m.board,&m.ldp)) {
            RoutePhase phase=settle_victory(&m,&g,&live);int score=0;player_one_score(&m.board,&score);
            bool ok=phase==ROUTE_VICTORY && (!miss_target || (missed && losses==1));
            printf("{\"type\":\"watch_replay\",\"verified\":%s,\"mode\":%u,\"score\":%d,\"moves\":%u,\"detour_applied\":%s,\"differences\":%u,\"intentional_death\":%s,\"losses\":%u}\n",ok?"true":"false",mode,score,moves_count,detour_applied?"true":"false",detour_seen,missed?"true":"false",losses);route_monitor=NULL;return ok?0:3;
        }
        if(m.board.cycles>=guide) {
            selected=(ArcadeMoveSelection){0,false,0};
            if(m.ldp.state==LDP_PLAYING)selected=arcade_select_profile(policy,strategy,m.board.ram,m.ldp.frame);
            uint32_t state=arcade_rom_state(m.board.ram[14],m.board.ram[15],ace?move_branch(&m):0);
            if(detour_target && m.ldp.state==LDP_PLAYING) {
                ArcadeMoveSelection other=arcade_select_profile(policy,other_strategy,m.board.ram,m.ldp.frame);
                if(!detour_applied && state!=last_difference &&
                   (selected.ready || other.ready) && selected.controls!=other.controls) {
                    last_difference=state;++detour_seen;
                    if(detour_seen==detour_target) {
                        detour_state=state;detour_applied=true;
                        printf("{\"type\":\"detour\",\"state\":%u,\"frame\":%d,\"original\":%u,\"replacement\":%u}\n",state,m.ldp.frame,selected.controls,other.controls);
                    }
                }
                if(detour_state==state)selected=other;
                else if(detour_applied)detour_state=UINT32_MAX;
            }
            if(selected.ready && (!was_ready || previous!=selected.window))pending=selected.controls;
            if(!selected.ready)pending=0;
            was_ready=selected.ready;previous=selected.window;guide+=131072;
            if(!selected.controls && state!=last_unknown){fprintf(stderr,"unrecognized state=%u scene=%u step=%u frame=%d\n",state,m.board.ram[14]&127,m.board.ram[15]&127,m.ldp.frame);last_unknown=state;}
        }
        if(m.board.cycles>=poll) {
            if(held && m.board.cycles>=release){if(queued==16){route_monitor=NULL;return 5;}queue[queued].control=held;queue[queued++].down=false;held=0;}
            if(!held && pending && miss_target && !missed && moves_count+1==miss_target) {
                missed=suppress=true;
                fprintf(stderr,"intentional miss at move=%u scene=%u step=%u frame=%d\n",moves_count+1,m.board.ram[14]&127,m.board.ram[15]&127,m.ldp.frame);
            }
            if(suppress)pending=0;
            if(!held && pending) {
                held=pending;pending=0;if(queued==16){route_monitor=NULL;return 5;}queue[queued].control=held;queue[queued++].down=true;release=m.board.cycles+400000;++moves_count;
                fprintf(stderr,"watch move=%u scene=%u step=%u frame=%d control=%u\n",moves_count,m.board.ram[14]&127,m.board.ram[15]&127,m.ldp.frame,held);
            }
            poll+=32000;
        }
        if(m.board.cycles>=input_at) {
            for(unsigned i=0;i<queued;i++)set_input(&m.board.inputs,queue[i].control==16?0:(int)queue[i].control,queue[i].down);
            queued=0;input_at+=68000;
        }
        uint64_t advance=m.board.cycles+SLICE_CYCLES;
        if(poll>m.board.cycles && poll<advance)advance=poll;
        if(guide>m.board.cycles && guide<advance)advance=guide;
        if(input_at>m.board.cycles && input_at<advance)advance=input_at;
        route_monitor=&live;monitored_run(&m,advance,&live);
    }
    printf("{\"type\":\"watch_replay\",\"verified\":false,\"mode\":%u,\"scene\":%u,\"step\":%u,\"frame\":%d,\"moves\":%u}\n",mode,m.board.ram[14]&127,m.board.ram[15]&127,m.ldp.frame,moves_count);
    route_monitor=NULL;return 3;
}
