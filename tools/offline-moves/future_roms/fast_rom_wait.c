/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later
 * Host-only exact closed-wait batching. Every proposed skip first checks a
 * complete original CPU iteration on a shadow CPU, including all registers.
 */
#include "games/cinematronics/board.h"
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>

extern CineBoard *fast_wait_board;
extern uint64_t fast_wait_deadline;
extern int uniform_fast_wait_allowed(const Z80 *);
static unsigned fast_wait_entry;
static bool fast_wait_configured,fast_wait_signature_checked;
static uint64_t fast_wait_loops,fast_wait_cycles,fast_wait_checks,fast_wait_not_fixed;

static void fast_wait_report(void) {
    printf("{\"type\":\"fast_wait_summary\",\"iterations_skipped\":%" PRIu64 ",\"cycles_skipped\":%" PRIu64 ",\"original_iteration_checks\":%" PRIu64 ",\"not_fixed\":%" PRIu64 "}\n",
           fast_wait_loops,fast_wait_cycles,fast_wait_checks,fast_wait_not_fixed);
}
void fast_rom_wait_configure(void) {
    if(fast_wait_configured)return;
    fast_wait_configured=true;
    const char *text=getenv("UNIFORM_WAIT_ENTRY");
    if(text) {
        char *end;unsigned long pc=strtoul(text,&end,10);
        if(!*text || *end || pc>65535){fprintf(stderr,"Invalid wait-loop entry\n");exit(2);}
        fast_wait_entry=(unsigned)pc;
    }
    atexit(fast_wait_report);
}
unsigned fast_rom_wait(Z80 *z) {
    if(!fast_wait_entry || z->pc!=fast_wait_entry)return 0;
    CineBoard *b=z->bus.ctx;
    if(b!=fast_wait_board || z!=&b->cpu || !uniform_fast_wait_allowed(z) || z->nmi ||
       (z->irq && z->iff1 && !z->ei_pending) || z->ei_pending || z->halted)return 0;
    static const uint8_t signature[]={0x3e,0x00,0xdd,0xbe,0x0c,0x20,0xf9,0xdd,0xbe,0x0d,0x20,0xf4,
                                    0xdd,0xbe,0x0e,0x20,0xef,0xdd,0xbe,0x0f,0x20,0xea};
    if(!fast_wait_signature_checked) {
        if(fast_wait_entry+sizeof signature>sizeof b->rom || memcmp(b->rom+fast_wait_entry,signature,sizeof signature)) {
            fprintf(stderr,"Original wait-loop signature differs\n");exit(3);
        }
        fast_wait_signature_checked=true;
    }
    unsigned ix=((unsigned)z->ixh<<8)|z->ixl;
    if(ix<0xa000 || ix+15>=0xa400)return 0;
    unsigned active=0;
    while(active<4 && !b->ram[ix-0xa000+12+active])++active;
    if(active==4)return 0;
    unsigned cycles=38+26*active,m1=4+3*active;
    uint64_t end=fast_wait_deadline<b->next_irq?fast_wait_deadline:b->next_irq;
    if(end<=b->cycles)return 0;
    uint64_t iterations=(end-b->cycles)/cycles;
    if(iterations<2)return 0;
    if(iterations>INT_MAX/cycles)iterations=INT_MAX/cycles;
    Z80 shadow=*z;
    unsigned elapsed=0,steps=0;
    do {
        elapsed+=(unsigned)z80_step(&shadow);++steps;
    } while(shadow.pc!=fast_wait_entry && shadow.pc!=fast_wait_entry+22 && steps<12);
    ++fast_wait_checks;
    unsigned delta=(shadow.r-z->r)&127;
    shadow.r=z->r;
    if(elapsed!=cycles || delta!=m1 || memcmp(&shadow,z,sizeof shadow)) {
        ++fast_wait_not_fixed;return 0;
    }
    z->r=(uint8_t)((z->r&128)|((z->r+iterations*m1)&127));
    fast_wait_loops+=iterations;fast_wait_cycles+=iterations*cycles;
    return (unsigned)(iterations*cycles);
}
