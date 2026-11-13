/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Bit-exact MPEG-2 half-pixel prediction, using ARMv7/AArch64 NEON.
 * Four-pixel interpolation must round only once, after the full sum.
 * Reference: https://arm-software.github.io/acle/neon_intrinsics/advsimd.html
 */
#include <stdint.h>
#include <arm_neon.h>
#include "mpeg2_internal.h"

#define predict_o(r,s) vld1_u8(r)
#define predict_x(r,s) vrhadd_u8(vld1_u8(r), vld1_u8((r)+1))
#define predict_y(r,s) vrhadd_u8(vld1_u8(r), vld1_u8((r)+(s)))
#define predict_xy(r,s) vrshrn_n_u16(vaddq_u16( \
    vaddl_u8(vld1_u8(r), vld1_u8((r)+1)), \
    vaddl_u8(vld1_u8((r)+(s)), vld1_u8((r)+(s)+1))), 2)
#define store_put(d,v) vst1_u8(d,v)
#define store_avg(d,v) vst1_u8(d,vrhadd_u8(vld1_u8(d),v))
#define MC(op,xy,w) \
static void MC_##op##_##xy##_##w##_neon(uint8_t *dest, const uint8_t *ref, int stride, int height) { \
    int row, x; \
    for (row = 0; row < height; ++row) { \
        for (x = 0; x < w; x += 8) { \
            uint8x8_t value = predict_##xy(ref+x,stride); \
            store_##op(dest+x,value); \
        } \
        ref += stride; dest += stride; \
    } \
}
#define MODES(op,w) MC(op,o,w) MC(op,x,w) MC(op,y,w) MC(op,xy,w)
MODES(put,16) MODES(put,8) MODES(avg,16) MODES(avg,8)
MPEG2_MC_EXTERN(neon)
