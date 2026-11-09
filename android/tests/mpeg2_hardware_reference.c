/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "mpeg2.h"
int main(int argc,char**argv){
 if(argc<4)return 2;
 FILE*f=fopen(argv[1],"rb");if(!f)return 2;fseek(f,0,SEEK_END);long n=ftell(f);rewind(f);uint8_t*b=malloc(n+4);if(!b||fread(b,1,n,f)!=(size_t)n)return 2;fclose(f);memcpy(b+n,"\0\0\1\xb7",4);
 unsigned header=0;while(header+4<n&&memcmp(b+header,"\0\0\1\xb8",4))header++;
 FILE*out=fopen(argv[2],"wb");
 for(int a=3;a<argc;a++){
  long offset=atol(argv[a]);mpeg2dec_t*d=mpeg2_init();mpeg2_buffer(d,b,b+header);while(mpeg2_parse(d)!=STATE_BUFFER){}
  mpeg2_buffer(d,b+offset,b+n+4);unsigned count=0;
  for(;;){mpeg2_state_t s=mpeg2_parse(d);if(s==STATE_BUFFER)break;const mpeg2_info_t*i=mpeg2_info(d);
   if((s==STATE_SLICE||s==STATE_END||s==STATE_INVALID_END)&&i->display_fbuf){
    for(int x=7;x>=0;x--)fputc((offset>>(x*8))&255,out);for(int x=3;x>=0;x--)fputc((count>>(x*8))&255,out);
    for(int y=0;y<480;y+=16)for(int x=0;x<720;x+=16)fputc(i->display_fbuf->buf[0][y*i->sequence->width+x],out);
    ++count;
   }
  }mpeg2_close(d);
 }fclose(out);free(b);return 0;
}
