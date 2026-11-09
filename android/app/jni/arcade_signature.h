/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef HYPSEUS_ARCADE_SIGNATURE_H
#define HYPSEUS_ARCADE_SIGNATURE_H
#include <stddef.h>
#include <stdint.h>

/* Cinematronics input table, 16 records of 16 bytes. ROMs reuse these RAM
 * slots without clearing unused outcome bytes or scratch space after a death.
 * Hash only the input descriptor, window count and outcomes actually selected
 * by those windows. Timers, unused selectors/outcomes and padding are not scene
 * identity. Keep descriptor flags: their semantics may affect accepted inputs.
 * Domain/version bytes distinguish this contract from the legacy raw hash. */
static inline uint64_t arcade_cine_signature(const uint8_t *table, size_t size) {
    if (!table || size < 256) return 0;
    uint64_t h = UINT64_C(14695981039346656037);
    const uint8_t domain[] = {'C', 'I', 'N', 'E', 2};
    for (size_t i=0;i<sizeof domain;i++) h=(h^domain[i])*UINT64_C(1099511628211);
    for (unsigned e=0;e<16;e++) {
        const uint8_t *x=table+16*e;
        if (!(x[0]&0x80)) break;
        unsigned count=x[1]&3;
        h=(h^x[0])*UINT64_C(1099511628211);
        h=(h^count)*UINT64_C(1099511628211);
        for (unsigned w=0;w<count;w++)
            h=(h^x[2+((x[1]>>(2+2*w))&3)])*UINT64_C(1099511628211);
    }
    return h;
}
#endif
