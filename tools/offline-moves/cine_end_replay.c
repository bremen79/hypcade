/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later
 * Exact DL1 replay, then observe the original successful end handler.
 * The caller supplies CRC-derived footer/end metadata, never injected state.
 */
#include <stdbool.h>
static bool cine_completion(void *);
#define HYPCADE_REPLAY_COMPLETION cine_completion
#define HYPCADE_SEARCH_NO_MAIN
#include "score_routes.c"
static unsigned end_pc,winning_frame[2];
static bool observed_success;
static CineBoard *replay_board;
static uint8_t (*completion_read)(void *,uint16_t);
static uint8_t observe_end(void *ctx,uint16_t address) {
    CineBoard *b=ctx;
    if(!replay_board)replay_board=b;
    if(b==replay_board && address==end_pc && b->cpu.pc==(uint16_t)(address+1)) {
        unsigned iy=((unsigned)b->cpu.iyh<<8)|b->cpu.iyl;
        if(iy>=0xa000 && iy+16<=0xa400) {
            const uint8_t *r=b->ram+iy-0xa000;
            unsigned frame=r[3]|(r[4]<<8);
            fprintf(stderr,"ROM end handler: IY=%04x flags=%02x source=%u frame=%u\n",iy,r[0],r[2]&127,frame);
            if((r[0]&63)==47 && (frame==winning_frame[0] || frame==winning_frame[1]))observed_success=true;
        }
    }
    return completion_read(ctx,address);
}
static bool cine_completion(void *source) {
    if(replay_board!=&((Machine *)source)->board) {
        fprintf(stderr,"End observer did not follow the physical replay machine\n");return false;
    }
    if(observed_success) {
        printf("{\"type\":\"rom_end\",\"verified\":true,\"handler_pc\":%u,\"additional_inputs\":0,\"during_replay\":true}\n",end_pc);
        return true;
    }
    Machine m=*(Machine *)source;connect_machine(&m);
    replay_board=&m.board;
    int lives=player_one_lives(&m.board);
    memset(&m.board.inputs,0,sizeof m.board.inputs);
    m.board.cpu.bus.read=observe_end;
    uint64_t deadline=m.board.cycles+60*(uint64_t)CINE_CPU_HZ;
    while(!observed_success && m.board.cycles<deadline) {
        run_until(&m,m.board.cycles+CINE_CPU_HZ/1000);
        int current_lives=player_one_lives(&m.board);
        if(!observed_success && current_lives>=0 && current_lives<lives) {
            fprintf(stderr,"Life display changed before end: %d -> %d, RAM=%02x PC=%04x\n",
                    lives,current_lives,m.board.ram[0x31],m.board.cpu.pc);
            break;
        }
    }
    unsigned iy=((unsigned)m.board.cpu.iyh<<8)|m.board.cpu.iyl;
    fprintf(stderr,"End observation: PC=%04x IY=%04x scene=%u step=%u frame=%d cycles=%" PRIu64 "\n",
            m.board.cpu.pc,iy,m.board.ram[14]&127,m.board.ram[15],m.ldp.frame,m.board.cycles);
    if(iy>=0xa000 && iy+16<=0xa400) {
        const uint8_t *r=m.board.ram+iy-0xa000;
        fprintf(stderr,"Footer: flags=%02x source=%u frame=%u duration=%u\n",r[0],r[2]&127,
                r[3]|(r[4]<<8),r[14]|(r[15]<<8));
    }
    printf("{\"type\":\"rom_end\",\"verified\":%s,\"handler_pc\":%u,\"additional_inputs\":0}\n",
           observed_success?"true":"false",end_pc);
    return observed_success;
}
int main(int argc,char **argv) {
    const char *pc=getenv("HYPCADE_END_PC"),*first=getenv("HYPCADE_END_FRAME0"),*second=getenv("HYPCADE_END_FRAME1");
    if(!pc || !first || !second)return 2;
    end_pc=(unsigned)strtoul(pc,NULL,10);winning_frame[0]=(unsigned)strtoul(first,NULL,10);winning_frame[1]=(unsigned)strtoul(second,NULL,10);
    if(end_pc>65535 || winning_frame[0]>65535 || winning_frame[1]>65535)return 2;
    RouteGraph graph={0};
    if(!parse_options(&graph.options,argc,argv) || !graph.options.replay ||
       !strcmp(graph.options.game,"ace") || !strcmp(graph.options.game,"sae"))return 2;
    graph.nodes=calloc(1,sizeof *graph.nodes);if(!graph.nodes)return 1;
    int result=3;
    if(graph_boot(&graph)) {
        completion_read=graph.base.board.cpu.bus.read;graph.base.board.cpu.bus.read=observe_end;
        result=graph_replay(&graph);
    }
    route_monitor=NULL;free(graph.nodes);return result;
}
