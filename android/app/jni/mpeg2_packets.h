/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <cstdio>
#include <cstdint>
#include <vector>
// Frame-aligned MPEG-2 elementary stream input; memory capped at 4 MiB/unit.
class Mpeg2Packets {
    FILE *file=nullptr;
    uint8_t input[65536];
    size_t pos=0,length=0;
    std::vector<uint8_t> prefix,pending,packet;
    uint64_t gop=0; int64_t highest=-1;
    int byte();
public:
    Mpeg2Packets(const char *path,uint64_t offset,const uint8_t *header,size_t header_size);
    ~Mpeg2Packets();
    Mpeg2Packets(const Mpeg2Packets&)=delete;
    Mpeg2Packets& operator=(const Mpeg2Packets&)=delete;
    // Returns false on EOF; throws on I/O, invalid/oversized data or small buffers.
    bool read(uint8_t *destination,size_t capacity,size_t &size,uint32_t &frame);
};
