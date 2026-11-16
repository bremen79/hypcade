/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later
 * Exact host-only released-input loop cache. A shadow original-CPU iteration
 * must restore every CPU/RAM byte except R; no external writes, device reads
 * or LD A,R / LD R,A are permitted. IRQ and player slice boundaries remain.
 */
#include "games/cinematronics/board.h"
#include <inttypes.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern CineBoard *fast_poll_board;
extern uint64_t fast_poll_deadline;
static unsigned poll_entry;
static bool configured,valid;
static Z80 cached_cpu;
static uint8_t cached_ram[2048];
static unsigned cached_cycles,cached_m1;
static uint64_t checks,hits,skipped,forbidden_checks,not_fixed;
static uint64_t forbidden_reads[8],forbidden_writes;
typedef struct {const CineBoard *board;Z80 *cpu;uint8_t ram[2048];bool forbidden;} PollShadow;

static void report(void) {
    printf("{\"type\":\"fast_poll\",\"checks\":%" PRIu64 ",\"cache_hits\":%" PRIu64 ",\"cycles_skipped\":%" PRIu64 ",\"forbidden_checks\":%" PRIu64 ",\"not_fixed\":%" PRIu64 ",\"read_groups\":[",
        checks,hits,skipped,forbidden_checks,not_fixed);
    for(unsigned i=0;i<8;i++)printf("%s%" PRIu64,i?",":"",forbidden_reads[i]);
    printf("],\"forbidden_writes\":%" PRIu64 "}\n",forbidden_writes);
}
void fast_rom_poll_configure(void) {
    if(configured)return;
    configured=true;const char *s=getenv("UNIFORM_POLL_ENTRY");
    if(s){char *end;unsigned long pc=strtoul(s,&end,10);if(!*s || *end || pc>65535)exit(2);poll_entry=(unsigned)pc;}
    atexit(report);
}
static uint8_t shadow_read(void *ctx,uint16_t address) {
    PollShadow *s=ctx;
    if(address<0xa000) {
        if((unsigned)address+1<sizeof s->board->rom && s->cpu->pc==(uint16_t)(address+1) &&
           s->board->rom[address]==0xed && (s->board->rom[address+1]==0x5f || s->board->rom[address+1]==0x4f))s->forbidden=true;
        return s->board->rom[address];
    }
    if(address<0xc000)return s->ram[address&0x7ff];
    if(address<0xe000 && (address&0x38)==8)return 255; /* all controls released */
    ++forbidden_reads[(address&0x38)/8];s->forbidden=true;return 255;
}
static void shadow_write(void *ctx,uint16_t address,uint8_t value) {
    PollShadow *s=ctx;
    if(address>=0xa000 && address<0xc000)s->ram[address&0x7ff]=value;
    else {++forbidden_writes;s->forbidden=true;}
}
static uint8_t shadow_in(void *ctx,uint16_t port) {(void)port;((PollShadow*)ctx)->forbidden=true;return 255;}
static void shadow_out(void *ctx,uint16_t port,uint8_t value) {(void)port;(void)value;((PollShadow*)ctx)->forbidden=true;}
static Z80 key(Z80 z) {z.r=0;z.bus.ctx=NULL;return z;}

unsigned fast_rom_poll(Z80 *z) {
    if(!poll_entry || z->pc!=poll_entry || !fast_poll_board || z!=&fast_poll_board->cpu)return 0;
    CineBoard *b=fast_poll_board;
    CineInputs empty={0};
    if(memcmp(&b->inputs,&empty,sizeof empty) || z->nmi || (z->irq && z->iff1 && !z->ei_pending) ||
       z->ei_pending || z->halted)return 0;
    uint64_t end=fast_poll_deadline<b->next_irq?fast_poll_deadline:b->next_irq;
    if(end<=b->cycles)return 0;
    Z80 before=key(*z);
    if(!valid || memcmp(&cached_cpu,&before,sizeof before) || memcmp(cached_ram,b->ram,sizeof cached_ram)) {
        PollShadow memory={.board=b};memcpy(memory.ram,b->ram,sizeof memory.ram);
        Z80 shadow=*z;memory.cpu=&shadow;
        shadow.bus=(Z80Bus){&memory,shadow_read,shadow_write,shadow_in,shadow_out};
        unsigned cycles=0,steps=0;
        do {cycles+=(unsigned)z80_step(&shadow);++steps;}
        while(shadow.pc!=poll_entry && steps<4096 && !memory.forbidden);
        ++checks;
        if(memory.forbidden){++forbidden_checks;return 0;}
        unsigned delta=(shadow.r-z->r)&127;
        shadow.bus=z->bus;Z80 after=key(shadow);
        if(steps>=4096 || shadow.pc!=poll_entry || memcmp(&before,&after,sizeof before) ||
           memcmp(memory.ram,b->ram,sizeof memory.ram) || !cycles) {++not_fixed;return 0;}
        cached_cpu=before;memcpy(cached_ram,b->ram,sizeof cached_ram);
        cached_cycles=cycles;cached_m1=delta;valid=true;
    } else ++hits;
    uint64_t iterations=(end-b->cycles)/cached_cycles;
    if(iterations>INT_MAX/cached_cycles)iterations=INT_MAX/cached_cycles;
    if(!iterations)return 0;
    unsigned cycles=(unsigned)(iterations*cached_cycles);
    z->r=(uint8_t)((z->r&128)|((z->r+iterations*cached_m1)&127));skipped+=cycles;
    return cycles;
}
