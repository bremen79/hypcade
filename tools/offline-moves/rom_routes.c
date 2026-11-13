/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later
 * Execute ROM-derived scene policies with the real CPU, player and inputs.
 * No injected scenes, score changes, videos, audio, or real-time waits.
 */
#define HYPCADE_SEARCH_NO_MAIN
#include "score_routes.c"

typedef struct {unsigned scene,step,control,window,outcome,rank;} RomChoice;
static RomChoice choices[20000];
static unsigned choice_count;
typedef struct {RouteEdge edge;char from[33],to[33];} RomPlayStep;
static RomPlayStep played[2048];
static unsigned played_count;

static bool read_choices(const char *path) {
    FILE *f=fopen(path,"r");if(!f)return false;
    char header[128];if(!fgets(header,sizeof header,f) || strcmp(header,"HYPCADE_ROM_POLICY_V1\n")){fclose(f);return false;}
    while(choice_count<sizeof choices/sizeof *choices) {
        RomChoice *c=&choices[choice_count];
        int n=fscanf(f,"%u %u %u %u %u %u",&c->scene,&c->step,&c->control,&c->window,&c->outcome,&c->rank);
        if(n==EOF){fclose(f);return choice_count>0;}
        if(n!=6 || c->scene>127 || c->step>127 || c->window>=192 || c->outcome>255 ||
           (c->control && c->control!=1 && c->control!=2 && c->control!=4 && c->control!=8 && c->control!=16))break;
        ++choice_count;
    }
    fclose(f);return false;
}
static void state_text(char out[33],const Machine *m,const RouteGraph *g,RoutePhase phase) {
    StateKey key;machine_key(&key,m,g,phase);key_text(out,key.a,key.b);
}
static bool save_trace(const char *path,const RouteGraph *g,const Machine *m) {
    FILE *f=fopen(path,"w");if(!f)return false;
    char root[33],final[33];key_text(root,g->nodes[0].hash_a,g->nodes[0].hash_b);state_text(final,m,g,ROUTE_VICTORY);
    int score=0;player_one_score(&m->board,&score);unsigned moves=0;
    for(unsigned i=0;i<played_count;i++)moves+=played[i].edge.control!=0;
    fprintf(f,"HYPCADE_ROUTE_V2 %s %s %u %d %u\n",root,final,played_count,score,moves);
    for(unsigned i=0;i<played_count;i++) {
        RomPlayStep *s=&played[i];RouteEdge *e=&s->edge;
        fprintf(f,"%u %" PRIu64 " %" PRIu64 " %" PRIu64 " %s %s %u\n",
                e->control,e->press_cycle,e->release_cycle,e->until_cycle,s->from,s->to,e->terminal_proof?1:0);
    }
    return fclose(f)==0;
}
/* Follow deferred acceptance without changing the replay checkpoint. A
 * prompt can change before the ROM consumes the move. Compare the eventual
 * scene/step against a simultaneous no-input execution, not just that prompt. */
static bool rom_effective(const Machine *source,const Machine *result,RouteGraph *g,const RouteEdge *edge,RoutePhase phase) {
    if(phase==ROUTE_VICTORY || (edge->after>edge->before && edge->after>edge->plain))return true;
    Machine pressed=*result,plain=*source;connect_machine(&pressed);connect_machine(&plain);
    unsigned scene=source->board.ram[14]&127,step=source->board.ram[15]&127;
    RouteMonitor monitor;monitor_start(&monitor,&pressed);
    uint64_t limit=pressed.board.cycles+30*(uint64_t)CINE_CPU_HZ;
    while(!monitor.death && pressed.board.cycles<limit &&
          (pressed.board.ram[14]&127)==scene && (pressed.board.ram[15]&127)==step)
        monitored_run(&pressed,pressed.board.cycles+SLICE_CYCLES,&monitor);
    if(monitor.death || pressed.board.cycles>=limit){route_monitor=NULL;return false;}
    monitored_run(&pressed,pressed.board.cycles+SETTLE_CYCLES,&monitor);route_monitor=NULL;
    run_until(&plain,pressed.board.cycles);
    int a=0,b=0;bool score_a=player_one_score(&pressed.board,&a),score_b=player_one_score(&plain.board,&b);
    (void)g;
    return !monitor.death && ((pressed.board.ram[14]&127)!=(plain.board.ram[14]&127) ||
           (pressed.board.ram[15]&127)!=(plain.board.ram[15]&127) ||
           player_one_lives(&pressed.board)>player_one_lives(&plain.board) ||
           (score_a && score_b && a>b));
}
static int play_tables(RouteGraph *g,const char *output) {
    Machine m;snapshot_restore(&m,&g->nodes[0].snapshot,g);
    char checkpoint[33];state_text(checkpoint,&m,g,ROUTE_DECISION);
    uint64_t checkpoint_cycle=m.board.cycles,last_trial[5]={0};unsigned trials=0,ignored=0,rejected=0;
    unsigned previous_scene=UINT_MAX,previous_step=UINT_MAX;
    RouteMonitor live;monitor_start(&live,&m);
    while(m.board.cycles<g->deadline && played_count<2048) {
        if(live.death || player_one_lives(&m.board)<(int)g->initial_lives)break;
        if(offline_won(&m.board,&m.ldp)) {
            RouteMonitor finish;monitor_start(&finish,&m);
            RoutePhase phase=settle_victory(&m,g,&finish);route_monitor=NULL;
            if(phase!=ROUTE_VICTORY)break;
            RomPlayStep *s=&played[played_count++];memset(s,0,sizeof *s);strcpy(s->from,checkpoint);
            s->edge.press_cycle=s->edge.release_cycle=checkpoint_cycle;s->edge.until_cycle=m.board.cycles;
            state_text(s->to,&m,g,phase);
            int score=0;player_one_score(&m.board,&score);
            if(!save_trace(output,g,&m))return 1;
            printf("{\"type\":\"rom_play\",\"finished\":true,\"no_life_loss\":true,\"score\":%d,\"moves\":%u,\"trials\":%u,\"ignored\":%u,\"rejected\":%u}\n",
                   score,played_count-1,trials,ignored,rejected);return 0;
        }
        unsigned scene=m.board.ram[0x0e]&127,step=m.board.ram[0x0f]&127;
        if(scene!=previous_scene || step!=previous_step) {
            fprintf(stderr,"ROM scene=%u step=%u frame=%d moves=%u trials=%u ignored=%u rejected=%u\n",scene,step,m.ldp.frame,played_count,trials,ignored,rejected);
            previous_scene=scene;previous_step=step;memset(last_trial,0,sizeof last_trial);
        }
        RomChoice *best=NULL;
        for(unsigned i=0;i<choice_count;i++)if(choices[i].scene==scene && choices[i].step==step &&
                (!best || choices[i].rank<best->rank))best=&choices[i];
        bool committed=false;
        if(best && best->control && m.ldp.state==LDP_PLAYING) {
            const unsigned controls[]={1,2,4,8,16};
            unsigned desired_rank=UINT_MAX;
            /* Choose among the ROM-listed windows currently open. Respect
             * the preferred route when its window has not opened yet. */
            for(unsigned ci=0;ci<5;ci++) {
                unsigned control=controls[ci];if(control!=best->control)continue;
                DecisionKey open;decision_key(&open,&m);if(!control_open(&open,control))continue;
                unsigned timing=move_timing(&m,control),slot=timing>>8;
                const uint8_t *r=m.board.ram+MOVE_LIST+16*(slot/3);
                if(!timing || r[12] || !r[13+slot%3])continue;
                unsigned outcome=r[2+((r[1]>>(2+2*(slot%3)))&3)];
                RomChoice *match=NULL;
                for(unsigned i=0;i<choice_count;i++) {
                    RomChoice *c=&choices[i];
                    if(c->scene==scene && c->step==step && c->control==control &&
                       c->window%3==slot%3 && c->outcome==outcome && (!match || c->rank<match->rank))match=c;
                }
                if(!match || match->rank>best->rank || match->rank>=desired_rank)continue;
                if(last_trial[ci] && m.board.cycles-last_trial[ci]<131072)continue;
                last_trial[ci]=m.board.cycles;desired_rank=match->rank;
                Machine trial=m;connect_machine(&trial);ScoreBaseline baseline;score_baseline_init(&baseline,&m,g);
                RouteEdge edge={.timing=timing,.outcome=outcome};bool admitted=false;
                RoutePhase phase=route_accepted_transition(&trial,g,control,&edge,&baseline,&admitted);++trials;
                if(!edge.seen){++ignored;continue;}
                if(!admitted || edge.life_lost || (phase!=ROUTE_DECISION && phase!=ROUTE_VICTORY) ||
                   !rom_effective(&m,&trial,g,&edge,phase)){++rejected;continue;}
                RomPlayStep *s=&played[played_count++];s->edge=edge;strcpy(s->from,checkpoint);
                state_text(s->to,&trial,g,phase);strcpy(checkpoint,s->to);
                checkpoint_cycle=trial.board.cycles;
                printf("{\"type\":\"rom_move\",\"scene\":%u,\"step\":%u,\"control\":%u,\"frame\":%d,\"timing\":%u,\"outcome\":%u,\"score_before\":%d,\"score_after\":%d,\"no_input_after\":%d,\"terminal_proof\":%s}\n",
                       scene,step,control,edge.frame,timing,outcome,edge.before,edge.after,edge.plain,edge.terminal_proof?"true":"false");
                m=trial;connect_machine(&m);monitor_start(&live,&m);committed=true;
                if(phase==ROUTE_VICTORY) {
                    int score=0;player_one_score(&m.board,&score);
                    if(!save_trace(output,g,&m))return 1;
                    printf("{\"type\":\"rom_play\",\"finished\":true,\"no_life_loss\":true,\"score\":%d,\"moves\":%u,\"trials\":%u,\"ignored\":%u,\"rejected\":%u}\n",
                           score,played_count,trials,ignored,rejected);return 0;
                }
                break;
            }
        }
        if(!committed) {
            route_monitor=&live;monitored_run(&m,m.board.cycles+SLICE_CYCLES,&live);
        }
    }
    route_monitor=NULL;
    printf("{\"type\":\"rom_play\",\"finished\":false,\"scene\":%u,\"step\":%u,\"frame\":%d,\"moves\":%u,\"life_lost\":%s,\"trials\":%u,\"ignored\":%u,\"rejected\":%u}\n",
           m.board.ram[14]&127,m.board.ram[15]&127,m.ldp.frame,played_count,live.death?"true":"false",trials,ignored,rejected);
    return 4;
}
#ifndef HYPCADE_ROM_ROUTES_NO_MAIN
int main(int argc,char **argv) {
    if(argc!=8 && argc!=9){fprintf(stderr,"usage: rom-routes ROM GAME SKILL START_DELAY POLICY TRACE MAX_SECONDS [DIFFICULTY]\n");return 2;}
    if(!read_choices(argv[5]))return 2;
    char *args[]={argv[0],argv[1],argv[2],argv[3],argv[4],argv[7],"--difficulty",argc==9?argv[8]:"0"};
    RouteGraph g={0};if(!parse_options(&g.options,8,args))return 2;
    g.nodes=calloc(1,sizeof *g.nodes);
    if(!g.nodes)return 1;
    setvbuf(stdout,NULL,_IOLBF,0);
    int result=graph_boot(&g) ? play_tables(&g,argv[6]) : 3;
    free(g.nodes);return result;
}

#endif
