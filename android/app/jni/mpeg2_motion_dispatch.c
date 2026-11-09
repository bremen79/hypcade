/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <stdint.h>
#include "mpeg2_internal.h"
#ifndef HYPSEUS_DECODER_TEST
#include <android/log.h>
#endif
extern void (*mpeg2_idct_copy)(int16_t *,uint8_t *,int);
extern void (*mpeg2_idct_add)(int,int16_t *,uint8_t *,int);
#if defined(__arm__)
#include <sys/auxv.h>
#include <asm/hwcap.h>
#endif
extern mpeg2_mc_t mpeg2_mc, mpeg2_mc_neon;
void mpeg2_mc_init_portable(uint32_t accel);

void mpeg2_mc_init(uint32_t accel) {
    mpeg2_mc_init_portable(accel);
#if defined(__aarch64__)
    /* Advanced SIMD is mandatory for Android's arm64 ABI. */
    mpeg2_mc = mpeg2_mc_neon;
#elif defined(__arm__)
    if (getauxval(AT_HWCAP) & HWCAP_NEON) mpeg2_mc = mpeg2_mc_neon;
#endif
}

void mpeg2_idct_init_portable(uint32_t accel);
void mpeg2_idct_copy_neon(int16_t *, uint8_t *, int);
void mpeg2_idct_add_neon(int, int16_t *, uint8_t *, int);
void mpeg2_idct_init(uint32_t accel) {
    /* Initializes clipping and the C scan order, also used by this NEON IDCT. */
    mpeg2_idct_init_portable(accel);
#if defined(__arm__)
    if (!(getauxval(AT_HWCAP) & HWCAP_NEON)) return;
#endif
    mpeg2_idct_copy = mpeg2_idct_copy_neon;
    mpeg2_idct_add = mpeg2_idct_add_neon;
#ifndef HYPSEUS_DECODER_TEST
    __android_log_print(ANDROID_LOG_INFO, "Hypseus", "MPEG-2 decoder: NEON motion compensation + IDCT columns");
#endif
}
