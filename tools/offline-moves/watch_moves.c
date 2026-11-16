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
/* Both CRC-pinned Space Ace programs use this accepted-input instruction.
 * Count original-ROM acceptance, separately from controller press attempts.
 * The end sites are shared with the independent SAE/A3 end replayer. */
static Machine *watch_live;
static uint8_t (*watch_original_read)(void *,uint16_t);
static unsigned watch_accepted,watch_scene,watch_step,watch_end_scene,watch_end_step;
static bool watch_end;
static FILE *watch_trace;
static Machine *watch_trace_machine;
static void watch_record_run(Machine *m,uint64_t deadline) {
    if(watch_trace && m==watch_trace_machine)fprintf(watch_trace,"R %" PRIu64 "\n",deadline);
}
static uint8_t watch_read(void *ctx,uint16_t address) {
    CineBoard *b=ctx;
    if(watch_live && b==&watch_live->board && b->cpu.pc==(uint16_t)(address+1)) {
        if(address==0x1850)++watch_accepted;
        if(address==0x15b2){watch_scene=b->ram[14]&127;watch_step=b->ram[15]&127;}
        if(address==0x15a2 && watch_scene==watch_end_scene && watch_step==watch_end_step)watch_end=true;
    }
    return watch_original_read(ctx,address);
}
static bool watch_finish(Machine *m) {
    if(watch_trace)fputs("C\n",watch_trace);
    memset(&m->board.inputs,0,sizeof m->board.inputs);
    uint64_t end=m->board.cycles+60*(uint64_t)CINE_CPU_HZ;
    while(!watch_end && m->board.cycles<end)run_until(m,m->board.cycles+SLICE_CYCLES);
    return watch_end;
}
static int watch_physical_replay(const char *path,Machine *m,RouteGraph *g,bool ace) {
    FILE *file=fopen(path,"r");if(!file)return 2;
    char line[256],version[40],expected[33],actual[33];unsigned calls=0,inputs=0;
    if(!fgets(line,sizeof line,file) || sscanf(line,"%39s %32s",version,expected)!=2 ||
       strcmp(version,"HYPCADE_WATCH_INPUTS_V1")){fclose(file);return 3;}
    state_text(actual,m,g,ROUTE_DECISION);
    if(strcmp(actual,expected)){fclose(file);return 3;}
    while(fgets(line,sizeof line,file)) {
        uint64_t deadline;unsigned control,down,accepted,end;int score;
        if(line[0]=='R' && sscanf(line,"R %" SCNu64,&deadline)==1) {
            if(deadline<m->board.cycles){fclose(file);return 3;}
            run_until(m,deadline);++calls;
        }else if(line[0]=='I' && sscanf(line,"I %u %u",&control,&down)==2) {
            if(down>1 || (control!=1 && control!=2 && control!=4 && control!=8 && control!=16)){
                fclose(file);return 3;
            }
            set_input(&m->board.inputs,control==16?0:(int)control,down!=0);++inputs;
        }else if(line[0]=='C')memset(&m->board.inputs,0,sizeof m->board.inputs);
        else if(line[0]=='E' && sscanf(line,"E %32s %d %u %u",expected,&score,&accepted,&end)==4) {
            int actual_score=0;state_text(actual,m,g,ROUTE_DECISION);
            bool ok=!strcmp(expected,actual) && player_one_score(&m->board,&actual_score) && actual_score==score &&
                    (!ace || (watch_accepted==accepted && watch_end && end));
            if(fgets(line,sizeof line,file))ok=false;
            fclose(file);
            printf("{\"type\":\"watch_physical_replay\",\"verified\":%s,\"score\":%d,\"accepted_commands\":%u,\"advances\":%u,\"input_events\":%u,\"final_hash\":\"%s\"}\n",
                ok?"true":"false",actual_score,watch_accepted,calls,inputs,actual);
            return ok?0:3;
        }else {fclose(file);return 3;}
    }
    fclose(file);return 3;
}
int main(int argc,char **argv) {
    if(argc<9 || argc>11)return 2;
    (void)play_tables;
    (void)read_choices;
    (void)read_timing_probes;
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
    static Machine m;m=g.base;connect_machine(&m);bool ace=m.board.game==CINE_SPACE_ACE;
    if(ace) {
        watch_live=&m;watch_original_read=m.board.cpu.bus.read;m.board.cpu.bus.read=watch_read;
        watch_scene=m.board.ram[14]&127;watch_step=m.board.ram[15]&127;
        watch_end_scene=!strcmp(g.options.game,"sae")?25:24;
        watch_end_step=!strcmp(g.options.game,"sae")?63:29;
    }
    const char *physical_replay=getenv("HYPCADE_WATCH_REPLAY");
    if(physical_replay)return watch_physical_replay(physical_replay,&m,&g,ace);
    const char *physical_record=getenv("HYPCADE_WATCH_RECORD");
    if(physical_record) {
        watch_trace=fopen(physical_record,"w");if(!watch_trace)return 2;
        char root[33];state_text(root,&m,&g,ROUTE_DECISION);
        fprintf(watch_trace,"HYPCADE_WATCH_INPUTS_V1 %s\n",root);
        watch_trace_machine=&m;offline_run_hook=watch_record_run;
    }
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
            if(ace)ok=watch_finish(&m) && ok;
            if(watch_trace) {
                char final[33];state_text(final,&m,&g,ROUTE_DECISION);
                fprintf(watch_trace,"E %s %d %u %u\n",final,score,watch_accepted,(unsigned)watch_end);
                if(fclose(watch_trace))ok=false;
                watch_trace=NULL;offline_run_hook=NULL;
            }
            printf("{\"type\":\"watch_replay\",\"verified\":%s,\"mode\":%u,\"score\":%d,\"moves\":%u,\"accepted_commands\":%u,\"rom_end\":%s,\"detour_applied\":%s,\"differences\":%u,\"intentional_death\":%s,\"losses\":%u}\n",ok?"true":"false",mode,score,moves_count,watch_accepted,ace?(watch_end?"true":"false"):"null",detour_applied?"true":"false",detour_seen,missed?"true":"false",losses);route_monitor=NULL;return ok?0:3;
        }
        if(m.board.cycles>=guide) {
            selected=(ArcadeMoveSelection){0,false,0};
            if(m.ldp.state==LDP_PLAYING)selected=arcade_select_profile(policy,strategy,m.board.ram);
            uint32_t state=arcade_rom_state(m.board.ram[14],m.board.ram[15],ace?move_branch(&m):0);
            if(detour_target && m.ldp.state==LDP_PLAYING) {
                ArcadeMoveSelection other=arcade_select_profile(policy,other_strategy,m.board.ram);
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
            for(unsigned i=0;i<queued;i++) {
                if(watch_trace)fprintf(watch_trace,"I %u %u\n",queue[i].control,(unsigned)queue[i].down);
                set_input(&m.board.inputs,queue[i].control==16?0:(int)queue[i].control,queue[i].down);
            }
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
