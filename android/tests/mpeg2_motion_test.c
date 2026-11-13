/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "mpeg2_internal.h"
extern void (*mpeg2_idct_copy)(int16_t *,uint8_t *,int);
extern void (*mpeg2_idct_add)(int,int16_t *,uint8_t *,int);
extern mpeg2_mc_t mpeg2_mc_neon, mpeg2_mc;
uint8_t mpeg2_scan_norm[64], mpeg2_scan_alt[64];
void mpeg2_idct_init_portable(uint32_t);
void mpeg2_idct_copy_neon(int16_t *,uint8_t *,int);
void mpeg2_idct_add_neon(int,int16_t *,uint8_t *,int);
static uint32_t seed = 0x12345678;
static unsigned random_byte(void) { seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5; return seed & 255; }
int main(void) {
    uint8_t ref[4096], expected[4096], actual[4096];
    unsigned test, i;
    mpeg2_mc_init(0);
    if (mpeg2_mc.put[0] != mpeg2_mc_neon.put[0]) { fputs("NEON dispatch not selected\n", stderr); return 1; }
    for (test=0; test<20000; ++test) {
        int stride = 24 + random_byte()%64, height = 1 + random_byte()%32;
        int offset = random_byte()%16, op;
        for(i=0;i<sizeof(ref);++i) ref[i] = test%4==0 ? 255 : test%4==1 ? 0 : random_byte();
        for (op=0;op<16;++op) {
            for(i=0;i<sizeof(actual);++i) actual[i] = expected[i] = random_byte();
            mpeg2_mc_fct *a = op<8 ? mpeg2_mc_c.put[op] : mpeg2_mc_c.avg[op-8];
            mpeg2_mc_fct *b = op<8 ? mpeg2_mc.put[op] : mpeg2_mc.avg[op-8];
            a(expected+offset,ref+offset,stride,height);
            b(actual+offset,ref+offset,stride,height);
            if(memcmp(expected,actual,sizeof(actual))) { fprintf(stderr,"Mismatch test %u op %d\n",test,op); return 1; }
        }
    }
    puts("PASS: 320000 NEON/scalar comparisons, all modes, unaligned strides, edge values and destination guards");
    mpeg2_idct_init_portable(0);
    for(test=0;test<100000;++test) {
        int16_t a[64],b[64];
        int stride=8+random_byte()%64, offset=random_byte()%16;
        int last=test%3==0 ? 129 : 0;
        for(i=0;i<64;++i) {
            int value=(int)((random_byte()<<8)|random_byte());
            a[i]=b[i]=test%3==0 && i!=0 && i!=63 ? 0 : value;
        }
        for(i=0;i<sizeof(actual);++i) actual[i]=expected[i]=random_byte();
        if(test&1) { mpeg2_idct_copy(a,expected+offset,stride); mpeg2_idct_copy_neon(b,actual+offset,stride); }
        else { mpeg2_idct_add(last,a,expected+offset,stride); mpeg2_idct_add_neon(last,b,actual+offset,stride); }
        if(memcmp(expected,actual,sizeof(actual)) || memcmp(a,b,sizeof(a))) {
            fprintf(stderr,"IDCT mismatch test %u last %d\n",test,last); return 1;
        }
    }
    puts("PASS: 100000 NEON/scalar IDCT comparisons, copy/add/DC, full int16 coefficients and block clearing");
    return 0;
}
