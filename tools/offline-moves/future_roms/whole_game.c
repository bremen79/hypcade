/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later
 * Whole-game search worker. Original CPU/player; no video, audio or real time.
 * Checkpoints belong to this process and are never imported from other runs.
 */
#define HYPCADE_ROM_ROUTES_NO_MAIN
#include "rom_routes.c"
#include <stdarg.h>

typedef struct {
    RouteSnapshot snapshot;
    uint64_t checkpoint_cycle;
    unsigned count;
    char checkpoint[33];
} WholeCheckpoint;

static FILE *checkpoint_store;
static bool has_origin, forced_active, saved_result;
static WholeCheckpoint origin;
static RomChoice forced_choice;
static int final_score;
static unsigned final_moves;
static uint64_t final_cycles;

static int audit_printf(const char *format,...) {
    /* Per-action records remain in the replay trace, not a growing RAM log. */
    (void)format;
    return 0;
}

static void whole_branch(const Machine *m,const RouteGraph *g,const char *checkpoint,
                         uint64_t checkpoint_cycle,const RomChoice *preferred) {
    if(forced_active || played_count>=2048)return;
    StateKey key;machine_key(&key,m,g,ROUTE_DECISION);
    unsigned moves=0;
    for(unsigned i=0;i<played_count;i++)moves+=played[i].edge.control!=0;
    int score=0;player_one_score(&m->board,&score);
    printf("{\"type\":\"node\",\"scene\":%u,\"step\":%u,\"moves\":%u,\"score\":%d,\"cycles\":%" PRIu64 ",\"bytes\":%zu,\"preferred\":",
           m->board.ram[14]&127,m->board.ram[15]&127,moves,score,m->board.cycles,
           sizeof(WholeCheckpoint)+played_count*sizeof *played);
    if(preferred)printf("[%u,%u,%u]",preferred->control,preferred->window%3,preferred->outcome);
    else printf("null");
    printf(",\"key\":\"");
    for(size_t i=0;i<key.used;i++)printf("%02x",key.bytes[i]);
    puts("\"}");fflush(stdout);
    char command[16];
    if(!fgets(command,sizeof command,stdin))exit(4);
    if(strcmp(command,"KEEP\n"))return;
    WholeCheckpoint point={0};snapshot_save(&point.snapshot,m);
    point.checkpoint_cycle=checkpoint_cycle;point.count=played_count;
    memcpy(point.checkpoint,checkpoint,sizeof point.checkpoint);
    if(fseeko(checkpoint_store,0,SEEK_END))exit(4);
    off_t offset=ftello(checkpoint_store);
    if(offset<0 || fwrite(&point,sizeof point,1,checkpoint_store)!=1 ||
       fwrite(played,sizeof *played,played_count,checkpoint_store)!=played_count ||
       fflush(checkpoint_store))exit(4);
    printf("{\"type\":\"checkpoint\",\"offset\":%" PRIu64 "}\n",(uint64_t)offset);
    fflush(stdout);
}

static bool whole_save_trace(const char *path,const RouteGraph *g,const Machine *m) {
    if(!player_one_score(&m->board,&final_score))return false;
    final_moves=0;
    for(unsigned i=0;i<played_count;i++)final_moves+=played[i].edge.control!=0;
    final_cycles=m->board.cycles;saved_result=true;
    return save_trace(path,g,m);
}

/* Built from the current production ROM-policy player with narrowly checked
 * substitutions. Its acceptance, no-input comparisons and timing stay shared. */
#include "whole_player.inc"

int main(int argc,char **argv) {
    if(argc!=10)return 2;
    (void)play_tables;
    (void)read_timing_probes;
    setvbuf(stdout,NULL,_IOLBF,0);
    char *base[]={argv[0],argv[1],argv[2],argv[3],argv[4],argv[9],"--difficulty",argv[5]};
    RouteGraph g={0};
    if(!parse_options(&g.options,8,base) || !read_choices(argv[6]))return 2;
    g.nodes=calloc(1,sizeof *g.nodes);
    if(!g.nodes || !graph_boot(&g))return 3;
    checkpoint_store=fopen(argv[7],"wb+");
    if(!checkpoint_store)return 4;
    printf("{\"type\":\"ready\",\"root_score\":%d,\"snapshot_bytes\":%zu}\n",g.nodes[0].score,sizeof(RouteSnapshot));
    char line[256];unsigned run=0;
    while(fgets(line,sizeof line,stdin)) {
        saved_result=false;played_count=0;has_origin=forced_active=false;
        if(!strcmp(line,"QUIT\n"))break;
        if(strcmp(line,"ROOT\n")) {
            uint64_t offset;unsigned control,window,outcome;char extra;
            if(sscanf(line,"RUN %" SCNu64 " %u %u %u %c",&offset,&control,&window,&outcome,&extra)!=4 ||
               offset>INT64_MAX || window>2 || outcome>255 ||
               (control && control!=1 && control!=2 && control!=4 && control!=8 && control!=16))return 4;
            if(fseeko(checkpoint_store,(off_t)offset,SEEK_SET) ||
               fread(&origin,sizeof origin,1,checkpoint_store)!=1 || origin.count>=2048 ||
               fread(played,sizeof *played,origin.count,checkpoint_store)!=origin.count)return 4;
            played_count=origin.count;has_origin=forced_active=true;
            unsigned scene=origin.snapshot.after_rom[14]&127,step=origin.snapshot.after_rom[15]&127;
            forced_choice=(RomChoice){.scene=scene,.step=step,.control=control,
                .window=window,.outcome=outcome,.skill=3,.score_gate=2};
        }
        int result=rollout_tables(&g,argv[8]);
        printf("{\"type\":\"result\",\"run\":%u,\"complete\":%s,\"score\":%d,\"moves\":%u,\"cycles\":%" PRIu64 ",\"trace_limit\":%s}\n",
               run++,result==0 && saved_result?"true":"false",saved_result?final_score:0,
               saved_result?final_moves:0,saved_result?final_cycles:0,played_count>=2048?"true":"false");
        fflush(stdout);
    }
    route_monitor=NULL;fclose(checkpoint_store);free(g.nodes);return 0;
}
