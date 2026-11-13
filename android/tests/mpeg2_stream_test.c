/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "mpeg2.h"
int main(int argc,char **argv) {
    FILE *f;
    long length;
    uint8_t *data;
    unsigned frames=0;
    uint64_t hash=UINT64_C(14695981039346656037);
    mpeg2dec_t *decoder;
    const mpeg2_info_t *info;
    if(argc!=2 || !(f=fopen(argv[1],"rb"))) return 2;
    if(fseek(f,0,SEEK_END) || (length=ftell(f))<0 || fseek(f,0,SEEK_SET)) return 2;
    data=malloc((size_t)length+4);
    if(!data || fread(data,1,length,f)!=(size_t)length) return 2;
    fclose(f);
    data[length]=0;data[length+1]=0;data[length+2]=1;data[length+3]=0xb7;
    decoder=mpeg2_init(); if(!decoder) return 2;
    info=mpeg2_info(decoder);
    mpeg2_buffer(decoder,data,data+length+4);
    for(;;) {
        mpeg2_state_t state=mpeg2_parse(decoder);
        if(state==STATE_BUFFER) break;
        if((state==STATE_SLICE || state==STATE_END || state==STATE_INVALID_END) && info->display_fbuf && info->sequence) {
            unsigned plane,i;
            for(plane=0;plane<3;++plane) {
                unsigned size=plane ? info->sequence->chroma_width*info->sequence->chroma_height : info->sequence->width*info->sequence->height;
                for(i=0;i<size;++i) {hash^=info->display_fbuf->buf[plane][i];hash*=UINT64_C(1099511628211);}
            }
            ++frames;
        }
    }
    mpeg2_close(decoder); free(data);
    printf("%u %016llx\n",frames,(unsigned long long)hash);
    return frames ? 0 : 1;
}
