/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* Hypcade adaptation/modification notice (2026-11-08).
 * Original authors and component licenses are retained; see MODIFICATIONS.md. */
/*
 * idct.c
 * Copyright (C) 2000-2003 Michel Lespinasse <walken@zoy.org>
 * Copyright (C) 1999-2000 Aaron Holtzman <aholtzma@ess.engr.uvic.ca>
 *
 * This file is part of mpeg2dec, a free MPEG-2 video stream decoder.
 * See http://libmpeg2.sourceforge.net/ for updates.
 *
 * mpeg2dec is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * mpeg2dec is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with mpeg2dec; if not, write to the Free Software Foundation, Inc.,
 * 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 */

/* Android NEON column transform and pixel output, GPL-3.0-or-later.
 * Retains libmpeg2's scalar row shortcut and exact intermediate rounding.
 * Four independent columns execute in parallel; the scan permutation is the
 * original C decoder's, initialized by mpeg2_idct_init_portable(). */
#include <stdint.h>
#include <arm_neon.h>
#include "mpeg2_internal.h"
#define W1 2841 /* 2048 * sqrt (2) * cos (1 * pi / 16) */
#define W2 2676 /* 2048 * sqrt (2) * cos (2 * pi / 16) */
#define W3 2408 /* 2048 * sqrt (2) * cos (3 * pi / 16) */
#define W5 1609 /* 2048 * sqrt (2) * cos (5 * pi / 16) */
#define W6 1108 /* 2048 * sqrt (2) * cos (6 * pi / 16) */
#define W7 565  /* 2048 * sqrt (2) * cos (7 * pi / 16) */

#if 0
#define BUTTERFLY(t0,t1,W0,W1,d0,d1)	\
do {					\
    t0 = W0 * d0 + W1 * d1;		\
    t1 = W0 * d1 - W1 * d0;		\
} while (0)
#else
#define BUTTERFLY(t0,t1,W0,W1,d0,d1)	\
do {					\
    int tmp = W0 * (d0 + d1);		\
    t0 = tmp + (W1 - W0) * d1;		\
    t1 = tmp - (W1 + W0) * d0;		\
} while (0)
#endif

static inline void idct_row (int16_t * const block)
{
    int d0, d1, d2, d3;
    int a0, a1, a2, a3, b0, b1, b2, b3;
    int t0, t1, t2, t3;

    /* shortcut */
    if (likely (!(block[1] | ((int32_t *)block)[1] | ((int32_t *)block)[2] |
		  ((int32_t *)block)[3]))) {
	uint32_t tmp = (uint16_t) (block[0] >> 1);
	tmp |= tmp << 16;
	((int32_t *)block)[0] = tmp;
	((int32_t *)block)[1] = tmp;
	((int32_t *)block)[2] = tmp;
	((int32_t *)block)[3] = tmp;
	return;
    }

    d0 = (block[0] << 11) + 2048;
    d1 = block[1];
    d2 = block[2] << 11;
    d3 = block[3];
    t0 = d0 + d2;
    t1 = d0 - d2;
    BUTTERFLY (t2, t3, W6, W2, d3, d1);
    a0 = t0 + t2;
    a1 = t1 + t3;
    a2 = t1 - t3;
    a3 = t0 - t2;

    d0 = block[4];
    d1 = block[5];
    d2 = block[6];
    d3 = block[7];
    BUTTERFLY (t0, t1, W7, W1, d3, d0);
    BUTTERFLY (t2, t3, W3, W5, d1, d2);
    b0 = t0 + t2;
    b3 = t1 + t3;
    t0 -= t2;
    t1 -= t3;
    b1 = ((t0 + t1) >> 8) * 181;
    b2 = ((t0 - t1) >> 8) * 181;

    block[0] = (a0 + b0) >> 12;
    block[1] = (a1 + b1) >> 12;
    block[2] = (a2 + b2) >> 12;
    block[3] = (a3 + b3) >> 12;
    block[4] = (a3 - b3) >> 12;
    block[5] = (a2 - b2) >> 12;
    block[6] = (a1 - b1) >> 12;
    block[7] = (a0 - b0) >> 12;
}


#define ADD vaddq_s32
#define SUB vsubq_s32
#define MUL(a,n) vmulq_n_s32(a,n)
#define LOAD(row) vmovl_s16(vld1_s16(block+8*(row)))
#define BUTTERFLY4(t0,t1,W0,W1,d0,d1) do { \
    int32x4_t tmp = MUL(ADD(d0,d1),W0); \
    t0 = ADD(tmp,MUL(d1,(W1)-(W0))); \
    t1 = SUB(tmp,MUL(d0,(W1)+(W0))); \
} while(0)
#define STORE(row,value) vst1_s16(block+8*(row),vmovn_s32(vshrq_n_s32(value,17)))
static inline void columns(int16_t *block) {
    int32x4_t d0,d1,d2,d3,a0,a1,a2,a3,b0,b1,b2,b3,t0,t1,t2,t3;
    d0=ADD(vshlq_n_s32(LOAD(0),11),vdupq_n_s32(65536));
    d1=LOAD(1); d2=vshlq_n_s32(LOAD(2),11); d3=LOAD(3);
    t0=ADD(d0,d2); t1=SUB(d0,d2);
    BUTTERFLY4(t2,t3,W6,W2,d3,d1);
    a0=ADD(t0,t2); a1=ADD(t1,t3); a2=SUB(t1,t3); a3=SUB(t0,t2);
    d0=LOAD(4); d1=LOAD(5); d2=LOAD(6); d3=LOAD(7);
    BUTTERFLY4(t0,t1,W7,W1,d3,d0);
    BUTTERFLY4(t2,t3,W3,W5,d1,d2);
    b0=ADD(t0,t2); b3=ADD(t1,t3);
    t0=SUB(t0,t2); t1=SUB(t1,t3);
    b1=MUL(vshrq_n_s32(ADD(t0,t1),8),181);
    b2=MUL(vshrq_n_s32(SUB(t0,t1),8),181);
    STORE(0,ADD(a0,b0)); STORE(1,ADD(a1,b1));
    STORE(2,ADD(a2,b2)); STORE(3,ADD(a3,b3));
    STORE(4,SUB(a3,b3)); STORE(5,SUB(a2,b2));
    STORE(6,SUB(a1,b1)); STORE(7,SUB(a0,b0));
}
static inline void transform(int16_t *block) {
    int i;
    for(i=0;i<8;++i) idct_row(block+8*i);
    columns(block); columns(block+4);
}
void mpeg2_idct_copy_neon(int16_t *block,uint8_t *dest,int stride) {
    int i;
    transform(block);
    for(i=0;i<8;++i) {
        vst1_u8(dest,vqmovun_s16(vld1q_s16(block)));
        vst1q_s16(block,vdupq_n_s16(0));
        dest+=stride; block+=8;
    }
}
void mpeg2_idct_add_neon(int last,int16_t *block,uint8_t *dest,int stride) {
    int i;
    if(last==129 && (block[0] & (7<<4)) != (4<<4)) {
        int16x8_t dc=vdupq_n_s16((block[0]+64)>>7);
        block[0]=block[63]=0;
        for(i=0;i<8;++i) {
            int16x8_t old=vreinterpretq_s16_u16(vmovl_u8(vld1_u8(dest)));
            vst1_u8(dest,vqmovun_s16(vaddq_s16(old,dc)));
            dest+=stride;
        }
    } else {
        transform(block);
        for(i=0;i<8;++i) {
            int16x8_t old=vreinterpretq_s16_u16(vmovl_u8(vld1_u8(dest)));
            vst1_u8(dest,vqmovun_s16(vaddq_s16(old,vld1q_s16(block))));
            vst1q_s16(block,vdupq_n_s16(0));
            dest+=stride; block+=8;
        }
    }
}
