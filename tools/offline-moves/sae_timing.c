/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later
 * Exact timing primitive for the executable ROM rules. No media, wall time,
 * graph enumeration, patched ROM or user-supplied refresh-register values.
 */
#define HYPCADE_SEARCH_NO_MAIN
#include "score_routes.c"

#define TIMING_EVENTS 128
/* Events are emitted at actual instruction fetches, before execution. */
enum { TIMING_READY=1, TIMING_OUTCOME, TIMING_REFRESH, TIMING_RESTART, TIMING_SUCCESS, TIMING_ACCEPTED };
typedef struct {
    uint64_t cycle;
    unsigned kind,scene,step,episode,outcome,control,refresh;
    int score,lives,slot,window;
    uint8_t ram[1024];
} TimingEvent;
typedef struct {
    RouteGraph graph;
    Machine live,saved;
    unsigned scene,step,accepted_control;
    unsigned saved_scene,saved_step,saved_control;
    bool success,saved_success,has_saved,overflow;
    uint64_t actual_press,actual_release;
    unsigned event_count;
    TimingEvent events[TIMING_EVENTS];
    uint8_t (*original_read)(void *,uint16_t);
} TimingSession;
static TimingSession *timing_active;

static void timing_ram(uint8_t *dest,const TimingSession *s) {
    const CineBoard *b=&s->live.board;
    memcpy(dest,b->ram,1024);
    unsigned iy=((unsigned)b->cpu.iyh<<8)|b->cpu.iyl;
    if(iy>=0xa000 && iy+16<=0xa400)memcpy(dest+0x200,b->ram+iy-0xa000,16);
    /* Source record identity, rather than its already-applied default step. */
    dest[14]=128|s->scene;dest[15]=s->step;
}
static void timing_emit(TimingSession *s,unsigned kind) {
    if(s->event_count==TIMING_EVENTS){s->overflow=true;return;}
    TimingEvent *e=&s->events[s->event_count++];memset(e,0,sizeof *e);
    e->cycle=s->live.board.cycles;e->kind=kind;
    e->scene=s->scene;e->step=s->step;e->episode=s->live.board.ram[0x36]&127;
    e->outcome=s->live.board.ram[0x12];e->control=s->accepted_control;
    e->slot=e->window=-1;
    if(kind==TIMING_ACCEPTED) {
        CineBoard *b=&s->live.board;unsigned ix=((unsigned)b->cpu.ixh<<8)|b->cpu.ixl;
        e->outcome=b->cpu.a;
        if(ix>=0xa0e0 && ix+16<=0xa800) {
            e->slot=(int)(ix-0xa0e0)/16;
            e->window=(int)(b->ram[ix-0xa000+1]&3)-(int)b->cpu.b;
        }
    }
    e->refresh=s->live.board.cpu.a;e->lives=player_one_lives(&s->live.board);
    e->score=-1;player_one_score(&s->live.board,&e->score);timing_ram(e->ram,s);
}
static uint8_t timing_read(void *ctx,uint16_t address) {
    TimingSession *s=timing_active;CineBoard *b=ctx;
    if(!s || b!=&s->live.board)return 255;
    if(b->cpu.pc==(uint16_t)(address+1)) {
        switch(address) {
        case 0x15b2:s->scene=b->ram[14]&127;s->step=b->ram[15]&127;break;
        case 0x1764:timing_emit(s,TIMING_READY);break;
        case 0x17d0:s->accepted_control=0;break;
        case 0x18b9: {
            unsigned ix=((unsigned)b->cpu.ixh<<8)|b->cpu.ixl;
            if(ix>=0xa000 && ix<0xa800){unsigned raw=b->ram[ix-0xa000]&15;s->accepted_control=raw?raw:16;}
            break;
        }
        case 0x1850: {
            unsigned ix=((unsigned)b->cpu.ixh<<8)|b->cpu.ixl;
            if(ix>=0xa000 && ix<0xa800){unsigned raw=b->ram[ix-0xa000]&15;s->accepted_control=raw?raw:16;}
            timing_emit(s,TIMING_ACCEPTED);break;
        }
        case 0x17d7:timing_emit(s,TIMING_OUTCOME);break;
        case 0x1eb3:if(b->ram[0x54]>=1 && b->ram[0x54]<=40)timing_emit(s,TIMING_REFRESH);break;
        case 0x1465:timing_emit(s,TIMING_RESTART);break;
        case 0x15a2:
            if(s->scene==25 && s->step==63){s->success=true;timing_emit(s,TIMING_SUCCESS);}
            break;
        default:break;
        }
    }
    return s->original_read(ctx,address);
}
static void timing_connect(TimingSession *s) {
    connect_machine(&s->live);
    s->live.board.cpu.bus.read=timing_read;
    timing_active=s;route_monitor=NULL;
}
static void timing_clear_events(TimingSession *s) {s->event_count=0;s->overflow=false;}
static bool timing_run(TimingSession *s,uint64_t until,bool finish) {
    while(s->live.board.cycles<until && !s->overflow && !(finish && s->success)) {
        uint64_t slice=until-s->live.board.cycles;
        if(slice>SLICE_CYCLES)slice=SLICE_CYCLES;
        run_until(&s->live,s->live.board.cycles+slice);
    }
    return !s->overflow;
}
void *sae_timing_open(const char *rom,const char *skill,unsigned difficulty,double delay) {
    if(!rom || !skill || difficulty>1 || !isfinite(delay) || delay<0 || delay>3600)return NULL;
    if(strcmp(skill,"cadet") && strcmp(skill,"captain") && strcmp(skill,"ace"))return NULL;
    TimingSession *s=calloc(1,sizeof *s);if(!s)return NULL;
    char difficulty_text[8],delay_text[64];
    snprintf(difficulty_text,sizeof difficulty_text,"%u",difficulty);
    snprintf(delay_text,sizeof delay_text,"%.17g",delay);
    char *args[]={"sae-timing",(char *)rom,"sae",(char *)skill,delay_text,"3600","--difficulty",difficulty_text};
    if(!parse_options(&s->graph.options,8,args)){free(s);return NULL;}
    s->graph.nodes=calloc(1,sizeof *s->graph.nodes);
    if(!s->graph.nodes || !graph_boot(&s->graph)){free(s->graph.nodes);free(s);return NULL;}
    snapshot_restore(&s->live,&s->graph.nodes[0].snapshot,&s->graph);
    s->original_read=s->live.board.cpu.bus.read;
    s->scene=s->live.board.ram[14]&127;s->step=s->live.board.ram[15]&127;
    timing_connect(s);fflush(stdout);return s;
}
void sae_timing_close(void *ptr) {
    TimingSession *s=ptr;if(!s)return;
    if(timing_active==s)timing_active=NULL;
    route_monitor=NULL;free(s->graph.nodes);ay8910_free(&s->graph.base.board.ay);free(s);
}
int sae_timing_action(void *ptr,unsigned control,uint64_t press,uint64_t release,uint64_t until) {
    TimingSession *s=ptr;
    if(!s || control>16 || press<s->live.board.cycles || release<press || until<release || until>s->graph.deadline)return 0;
    timing_connect(s);timing_clear_events(s);
    if(!timing_run(s,press,false))return 0;
    s->actual_press=s->live.board.cycles;
    int input=control==16?0:(int)control;
    if(control)set_input(&s->live.board.inputs,input,true);
    bool held=timing_run(s,release,false);
    s->actual_release=s->live.board.cycles;
    if(control)set_input(&s->live.board.inputs,input,false);
    if(!held)return 0;
    return timing_run(s,until,false);
}
int sae_timing_wait(void *ptr,uint64_t until) {
    TimingSession *s=ptr;if(!s || until<s->live.board.cycles || until>s->graph.deadline)return 0;
    timing_connect(s);timing_clear_events(s);return timing_run(s,until,false);
}
int sae_timing_finish(void *ptr,uint64_t maximum_extra) {
    TimingSession *s=ptr;if(!s || s->live.board.cycles>s->graph.deadline || maximum_extra>s->graph.deadline-s->live.board.cycles)return 0;
    timing_connect(s);timing_clear_events(s);
    return timing_run(s,s->live.board.cycles+maximum_extra,true) && s->success;
}
int sae_timing_save(void *ptr) {
    TimingSession *s=ptr;if(!s)return 0;
    s->saved=s->live;s->saved_scene=s->scene;s->saved_step=s->step;s->saved_control=s->accepted_control;
    s->saved_success=s->success;s->has_saved=true;return 1;
}
int sae_timing_restore(void *ptr) {
    TimingSession *s=ptr;if(!s || !s->has_saved)return 0;
    s->live=s->saved;s->scene=s->saved_scene;s->step=s->saved_step;s->accepted_control=s->saved_control;
    s->success=s->saved_success;timing_connect(s);timing_clear_events(s);return 1;
}
unsigned sae_timing_event_count(void *ptr) {TimingSession *s=ptr;return s?s->event_count:0;}
int sae_timing_event(void *ptr,unsigned i,uint64_t *fields,uint8_t *ram) {
    TimingSession *s=ptr;if(!s || i>=s->event_count || s->overflow)return 0;
    const TimingEvent *e=&s->events[i];
    fields[0]=e->cycle;fields[1]=e->kind;fields[2]=e->scene;fields[3]=e->step;fields[4]=e->episode;
    fields[5]=e->outcome;fields[6]=e->control;fields[7]=e->refresh;fields[8]=e->score;fields[9]=e->lives;
    fields[10]=e->slot;fields[11]=e->window;
    memcpy(ram,e->ram,1024);return 1;
}
int sae_timing_state(void *ptr,uint64_t *fields,uint8_t *ram,char *hashes) {
    TimingSession *s=ptr;if(!s)return 0;CineBoard *b=&s->live.board;int score=-1;player_one_score(b,&score);
    fields[0]=b->cycles;fields[1]=b->cpu.pc;fields[2]=b->cpu.r;fields[3]=b->next_irq;
    fields[4]=s->live.ldp.frame;fields[5]=s->live.ldp.state;fields[6]=score;fields[7]=player_one_lives(b);
    fields[8]=b->ram[0x36]&127;fields[9]=s->scene;fields[10]=s->step;fields[11]=b->ram[0x37];
    timing_ram(ram,s);
    StateKey key;machine_key(&key,&s->live,&s->graph,ROUTE_DECISION);key_text(hashes,key.a,key.b);
    machine_key(&key,&s->live,&s->graph,ROUTE_VICTORY);key_text(hashes+33,key.a,key.b);
    return 1;
}
int sae_timing_action_times(void *ptr,uint64_t *fields) {
    TimingSession *s=ptr;if(!s)return 0;
    fields[0]=s->actual_press;fields[1]=s->actual_release;return 1;
}
uint64_t sae_timing_memory_bytes(void) {return sizeof(TimingSession)+sizeof(RouteNode);}
