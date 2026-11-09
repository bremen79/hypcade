/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "mpeg2_replay.h"
static_assert(sizeof(off_t)>=8,"MPEG-2 file offsets must remain 64-bit");
#include <algorithm>
#include <vector>
static bool display(mpeg2_state_t state, const mpeg2_info_t *info) {
    return (state==STATE_SLICE || state==STATE_END || state==STATE_INVALID_END) && info->display_fbuf;
}
mpeg2dec_t *mpeg2_replay(FILE *file, uint64_t start, uint64_t chunk_start,
    const uint8_t *header, size_t header_size, uint8_t *current, uint8_t *end,
    uint64_t displayed) {
    if(!file || chunk_start<start || fseeko(file,static_cast<off_t>(start),SEEK_SET))return nullptr;
    mpeg2dec_t *decoder=mpeg2_init();if(!decoder)return nullptr;
    if(header_size){mpeg2_buffer(decoder,const_cast<uint8_t *>(header),const_cast<uint8_t *>(header)+header_size);
        while(mpeg2_parse(decoder)!=STATE_BUFFER){} }
    std::vector<uint8_t> scratch(262144);
    uint64_t count=0,remaining=chunk_start-start;
    while(remaining) {
        size_t size=static_cast<size_t>(std::min<uint64_t>(remaining,scratch.size()));
        if(fread(scratch.data(),1,size,file)!=size){mpeg2_close(decoder);return nullptr;}
        mpeg2_buffer(decoder,scratch.data(),scratch.data()+size);
        for(;;){mpeg2_state_t state=mpeg2_parse(decoder);if(state==STATE_BUFFER)break;
            if(display(state,mpeg2_info(decoder)) && ++count>=displayed){mpeg2_close(decoder);return nullptr;}}
        remaining-=size;
    }
    mpeg2_buffer(decoder,current,end);
    for(;;){mpeg2_state_t state=mpeg2_parse(decoder);if(state==STATE_BUFFER)break;
        if(display(state,mpeg2_info(decoder)) && ++count==displayed)return decoder;}
    mpeg2_close(decoder);return nullptr;
}
