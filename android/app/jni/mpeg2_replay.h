/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <cstdint>
#include <cstdio>
#include <mpeg2.h>
// Restore the software decoder at exactly the parser display event which failed
// in hardware. On success its remaining input points into current (not scratch).
mpeg2dec_t *mpeg2_replay(FILE *file, uint64_t start, uint64_t chunk_start,
    const uint8_t *header, size_t header_size, uint8_t *current, uint8_t *end,
    uint64_t displayed);
