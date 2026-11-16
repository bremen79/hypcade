/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later
 * Execute ROM-derived scene policies with the real CPU, player and inputs.
 * No injected scenes, score changes, videos, audio, or real-time waits.
 */
#define HYPCADE_SEARCH_NO_MAIN
#include "score_routes.c"

typedef struct {unsigned scene,step,control,window,outcome,rank,skill,branch_mask,branch_value,score_gate;} RomChoice;
static RomChoice choices[20000];
static unsigned choice_count;
typedef struct {unsigned scene,step,control;uint64_t delay;} RomTimingProbe;
static RomTimingProbe timing_probes[64];
static unsigned timing_probe_count;
/* Optional witness construction only. Delays are physical input schedules;
 * independent replay has no access to these probes or to the policy. */
static bool read_timing_probes(const char *path) {
    FILE *f=fopen(path,"r");if(!f)return false;
    char header[64];
    if(!fgets(header,sizeof header,f) || strcmp(header,"HYPCADE_ROM_TIMING_V1\n")){fclose(f);return false;}
    while(timing_probe_count<64) {
        RomTimingProbe *p=&timing_probes[timing_probe_count];
        int n=fscanf(f,"%u %u %u %" SCNu64,&p->scene,&p->step,&p->control,&p->delay);
        if(n==EOF){fclose(f);return true;}
        if(n!=4 || p->scene>127 || p->step>127 || p->delay>CINE_CPU_HZ ||
           (p->control!=1 && p->control!=2 && p->control!=4 && p->control!=8 && p->control!=16))break;
        ++timing_probe_count;
    }
    fclose(f);return false;
}
typedef struct {RouteEdge edge;char from[33],to[33];} RomPlayStep;
static RomPlayStep played[2048];
static unsigned played_count;
static Machine *recovery_machine;
static uint8_t (*recovery_original_read)(void *,uint16_t);
static bool recovery_requested,recovery_started,recovery_ready;
static unsigned recovery_scene,recovery_step;
static uint8_t recovery_read(void *ctx,uint16_t address) {
    CineBoard *b=ctx;
    if(recovery_machine && b==&recovery_machine->board && b->cpu.pc==(uint16_t)(address+1)) {
        if(address==0x15b2){recovery_scene=b->ram[14]&127;recovery_step=b->ram[15]&127;}
        if(recovery_requested && address==0x1465)recovery_started=true;
        if(recovery_started && address==0x1764)recovery_ready=true;
    }
    return recovery_original_read(ctx,address);
}
static unsigned played_moves(void) {
    unsigned n=0;for(unsigned i=0;i<played_count;i++)n+=played[i].edge.control!=0;return n;
}

static bool read_choices(const char *path) {
    FILE *f=fopen(path,"r");if(!f)return false;
    char header[128];if(!fgets(header,sizeof header,f)){fclose(f);return false;}
    bool gated=!strcmp(header,"HYPCADE_ROM_POLICY_V3\n");
    bool contextual=gated || !strcmp(header,"HYPCADE_ROM_POLICY_V2\n");
    if(!contextual && strcmp(header,"HYPCADE_ROM_POLICY_V1\n")){fclose(f);return false;}
    while(choice_count<sizeof choices/sizeof *choices) {
        RomChoice *c=&choices[choice_count];
        c->skill=3;c->branch_mask=0;c->branch_value=0;c->score_gate=2;
        int n=gated ? fscanf(f,"%u %u %u %u %u %u %u %u %u %u",&c->scene,&c->step,&c->control,&c->window,&c->outcome,&c->rank,&c->skill,&c->branch_mask,&c->branch_value,&c->score_gate) : contextual ? fscanf(f,"%u %u %u %u %u %u %u %u %u",&c->scene,&c->step,&c->control,&c->window,&c->outcome,&c->rank,&c->skill,&c->branch_mask,&c->branch_value) :
            fscanf(f,"%u %u %u %u %u %u",&c->scene,&c->step,&c->control,&c->window,&c->outcome,&c->rank);
        if(n==EOF){fclose(f);return choice_count>0;}
        if(n!=(gated?10:contextual?9:6) || c->scene>127 || c->step>127 || c->window>=192 || c->outcome>255 || c->skill>3 || c->score_gate>2 ||
           c->branch_mask>65535 || c->branch_value>65535 || (c->branch_value&~c->branch_mask) ||
           (c->control && c->control!=1 && c->control!=2 && c->control!=4 && c->control!=5 && c->control!=6 && c->control!=8 && c->control!=9 && c->control!=10 && c->control!=16))break;
        ++choice_count;
    }
    fclose(f);return false;
}
static bool choice_context(const RomChoice *c,const Machine *m) {
    unsigned branch=move_branch(m);
    return (c->skill==3 || c->skill==m->board.ram[0xd4]) &&
        (c->score_gate==2 || c->score_gate==((m->board.ram[10]>>1)&1)) &&
        (branch&c->branch_mask)==c->branch_value;
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
    const bool verbose=getenv("HYPCADE_ROM_TRIALS")!=NULL;
    Machine m;snapshot_restore(&m,&g->nodes[0].snapshot,g);
    unsigned miss_at=0;const char *miss=getenv("HYPCADE_ROM_MISS_AT");
    if(miss){char *end;unsigned long value=strtoul(miss,&end,10);if(!*miss || *end || value<1 || value>1000)return 2;miss_at=(unsigned)value;}
    bool withholding=false,recovered=false,death_seen=false;
    unsigned detour_at=0,opportunities=0;const char *detour=getenv("HYPCADE_ROM_DETOUR_AT");
    if(detour){char *end;unsigned long value=strtoul(detour,&end,10);if(!*detour || *end || value<1 || value>1000)return 2;detour_at=(unsigned)value;}
    if(miss_at && detour_at)return 2;
    bool detoured=false,considered=false;RomChoice *deviation=NULL;
    recovery_machine=&m;recovery_original_read=m.board.cpu.bus.read;m.board.cpu.bus.read=recovery_read;
    char checkpoint[33];state_text(checkpoint,&m,g,ROUTE_DECISION);
    uint64_t checkpoint_cycle=m.board.cycles,last_trial[9]={0};unsigned trials=0,ignored=0,rejected=0;
    unsigned previous_scene=UINT_MAX,previous_step=UINT_MAX;
    RouteMonitor live;monitor_start(&live,&m);
    while(m.board.cycles<g->deadline && played_count<2048) {
        if(miss_at && !recovered && played_moves()+1==miss_at){withholding=true;recovery_requested=true;}
        int current_lives=player_one_lives(&m.board);
        if(live.death || (current_lives>=0 && current_lives<(int)g->initial_lives)) {
            if(!withholding || recovered || death_seen || current_lives!=(int)g->initial_lives-1)break;
            death_seen=true;--g->initial_lives;monitor_start(&live,&m);
        }
        if(withholding) {
            if(!recovery_ready){monitored_run(&m,m.board.cycles+SLICE_CYCLES,&live);continue;}
            RomPlayStep *s=&played[played_count++];memset(s,0,sizeof *s);strcpy(s->from,checkpoint);
            s->edge.press_cycle=s->edge.release_cycle=checkpoint_cycle;s->edge.until_cycle=m.board.cycles;
            state_text(s->to,&m,g,ROUTE_DECISION);strcpy(checkpoint,s->to);checkpoint_cycle=m.board.cycles;
            int score=0;player_one_score(&m.board,&score);
            printf("{\"type\":\"rom_resume\",\"cycle\":%" PRIu64 ",\"scene\":%u,\"step\":%u,\"score\":%d,\"lives\":%d}\n",
                   m.board.cycles,recovery_scene,recovery_step,score,player_one_lives(&m.board));
            withholding=false;recovered=true;recovery_requested=false;monitor_start(&live,&m);
        }
        if(offline_won(&m.board,&m.ldp)) {
            RouteMonitor finish;monitor_start(&finish,&m);
            RoutePhase phase=settle_victory(&m,g,&finish);route_monitor=NULL;
            if(phase!=ROUTE_VICTORY)break;
            RomPlayStep *s=&played[played_count++];memset(s,0,sizeof *s);strcpy(s->from,checkpoint);
            s->edge.press_cycle=s->edge.release_cycle=checkpoint_cycle;s->edge.until_cycle=m.board.cycles;
            state_text(s->to,&m,g,phase);
            int score=0;player_one_score(&m.board,&score);
            if(!save_trace(output,g,&m))return 1;
            printf("{\"type\":\"rom_play\",\"finished\":true,\"no_life_loss\":%s,\"score\":%d,\"moves\":%u,\"trials\":%u,\"ignored\":%u,\"rejected\":%u}\n",
                   recovered?"false":"true",score,played_moves(),trials,ignored,rejected);return 0;
        }
        unsigned scene=m.board.ram[0x0e]&127,step=m.board.ram[0x0f]&127;
        if(scene!=previous_scene || step!=previous_step) {
            fprintf(stderr,"ROM scene=%u step=%u frame=%d moves=%u trials=%u ignored=%u rejected=%u\n",scene,step,m.ldp.frame,played_count,trials,ignored,rejected);
            previous_scene=scene;previous_step=step;memset(last_trial,0,sizeof last_trial);
            considered=false;deviation=NULL;
        }
        RomChoice *best=NULL;
        for(unsigned i=0;i<choice_count;i++)if(choices[i].scene==scene && choices[i].step==step && choice_context(&choices[i],&m) &&
                (!best || choices[i].rank<best->rank))best=&choices[i];
        if(detour_at && !detoured && best && !considered) {
            RomChoice *alternative=NULL;
            for(unsigned i=0;i<choice_count;i++) {
                RomChoice *c=&choices[i];
                if(c->scene!=scene || c->step!=step || !choice_context(c,&m) || !c->control ||
                   c->rank<=best->rank || c->outcome==best->outcome)continue;
                const uint8_t *entry=m.board.ram+MOVE_LIST+16*(c->window/3);
                if(!(entry[0]&128) || !entry[13+c->window%3])continue;
                if(!alternative || c->rank<alternative->rank)alternative=c;
            }
            if(alternative) {
                considered=true;
                if(++opportunities==detour_at)deviation=alternative;
            }
        }
        if(deviation)best=deviation;
        bool committed=false;
        if(best && best->control && m.ldp.state==LDP_PLAYING) {
            const unsigned controls[]={1,2,4,5,6,8,9,10,16};
            unsigned desired_rank=UINT_MAX;
            /* Choose among the ROM-listed windows currently open. Respect
             * the preferred route when its window has not opened yet. */
            for(unsigned ci=0;ci<sizeof controls/sizeof *controls;ci++) {
                unsigned control=controls[ci];if(control!=best->control)continue;
                DecisionKey open;decision_key(&open,&m);if(!control_open(&open,control))continue;
                unsigned timing=move_timing(&m,control),slot=timing>>8;
                const uint8_t *r=m.board.ram+MOVE_LIST+16*(slot/3);
                if(!timing || r[12] || !r[13+slot%3])continue;
                unsigned outcome=r[2+((r[1]>>(2+2*(slot%3)))&3)];
                RomChoice *match=NULL;
                for(unsigned i=0;i<choice_count;i++) {
                    RomChoice *c=&choices[i];
                    if(c->scene==scene && c->step==step && c->control==control && choice_context(c,&m) &&
                       c->window%3==slot%3 && c->outcome==outcome && (!match || c->rank<match->rank))match=c;
                }
                if(!match || match->rank>best->rank || match->rank>=desired_rank)continue;
                if(last_trial[ci] && m.board.cycles-last_trial[ci]<131072)continue;
                last_trial[ci]=m.board.cycles;desired_rank=match->rank;
                Machine trial=m;connect_machine(&trial);ScoreBaseline baseline;score_baseline_init(&baseline,&m,g);
                for(unsigned pi=0;pi<timing_probe_count;pi++) {
                    const RomTimingProbe *p=&timing_probes[pi];
                    if(p->scene==scene && p->step==step && p->control==control) {
                        run_until(&trial,trial.board.cycles+p->delay);break;
                    }
                }
                RouteEdge edge={.timing=timing,.outcome=outcome};bool admitted=false;
                RoutePhase phase=route_accepted_transition(&trial,g,control,&edge,&baseline,&admitted);++trials;
                if(!edge.seen){++ignored;continue;}
                if(!admitted || edge.life_lost || (phase!=ROUTE_DECISION && phase!=ROUTE_VICTORY) ||
                   !rom_effective(&m,&trial,g,&edge,phase)){
                    if(verbose)fprintf(stderr,"Rejected action scene=%u step=%u control=%u frame=%d phase=%d seen=%d lost=%d accepted=%d score=%d->%d trial_scene=%u trial_step=%u trial_frame=%d lives=%d\n",
                        scene,step,control,edge.frame,phase,edge.seen,edge.life_lost,admitted,edge.before,edge.after,
                        trial.board.ram[14]&127,trial.board.ram[15]&127,trial.ldp.frame,player_one_lives(&trial.board));
                    ++rejected;continue;
                }
                RomPlayStep *s=&played[played_count++];s->edge=edge;strcpy(s->from,checkpoint);
                state_text(s->to,&trial,g,phase);strcpy(checkpoint,s->to);
                checkpoint_cycle=trial.board.cycles;
                if(deviation) {
                    printf("{\"type\":\"rom_detour\",\"scene\":%u,\"step\":%u,\"control\":%u,\"outcome\":%u,\"press_cycle\":%" PRIu64 "}\n",
                           scene,step,control,edge.outcome,edge.press_cycle);
                    detoured=true;deviation=NULL;
                }
                printf("{\"type\":\"rom_move\",\"scene\":%u,\"step\":%u,\"control\":%u,\"frame\":%d,\"timing\":%u,\"outcome\":%u,\"score_before\":%d,\"score_after\":%d,\"no_input_after\":%d,\"terminal_proof\":%s}\n",
                       scene,step,control,edge.frame,timing,outcome,edge.before,edge.after,edge.plain,edge.terminal_proof?"true":"false");
                m=trial;connect_machine(&m);monitor_start(&live,&m);committed=true;
                if(phase==ROUTE_VICTORY) {
                    int score=0;player_one_score(&m.board,&score);
                    if(!save_trace(output,g,&m))return 1;
                    printf("{\"type\":\"rom_play\",\"finished\":true,\"no_life_loss\":%s,\"score\":%d,\"moves\":%u,\"trials\":%u,\"ignored\":%u,\"rejected\":%u}\n",
                           recovered?"false":"true",score,played_moves(),trials,ignored,rejected);return 0;
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
    if(argc<8 || argc>10){fprintf(stderr,"usage: rom-routes ROM GAME SKILL START_DELAY POLICY TRACE MAX_SECONDS [DIFFICULTY [TIMING_PROBES]]\n");return 2;}
    if(!read_choices(argv[5]))return 2;
    if(argc==10 && !read_timing_probes(argv[9]))return 2;
    char *args[]={argv[0],argv[1],argv[2],argv[3],argv[4],argv[7],"--difficulty",argc>=9?argv[8]:"0"};
    RouteGraph g={0};if(!parse_options(&g.options,8,args))return 2;
    g.nodes=calloc(1,sizeof *g.nodes);
    if(!g.nodes)return 1;
    setvbuf(stdout,NULL,_IOLBF,0);
    int result=graph_boot(&g) ? play_tables(&g,argv[6]) : 3;
    free(g.nodes);return result;
}

#endif
