/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "mpeg2_replay.h"
#include <vector>
#include <cassert>
#include <algorithm>
#include <cstring>
#include <iostream>
static bool frame(mpeg2_state_t s,const mpeg2_info_t *i){return (s==STATE_SLICE||s==STATE_END||s==STATE_INVALID_END)&&i->display_fbuf;}
static uint64_t hash(const mpeg2_info_t *i){uint64_t h=14695981039346656037ull;
 for(int p=0;p<3;p++){size_t n=p?i->sequence->chroma_width*i->sequence->chroma_height:i->sequence->width*i->sequence->height;
  for(size_t j=0;j<n;j++){h^=i->display_fbuf->buf[p][j];h*=1099511628211ull;}}return h;}
int main(int argc,char**argv){assert(argc==2);FILE*f=fopen(argv[1],"rb");assert(f);fseek(f,0,SEEK_END);size_t size=ftell(f);rewind(f);
 std::vector<uint8_t> data(size+4);assert(fread(data.data(),1,size,f)==size);memcpy(data.data()+size,"\0\0\1\xb7",4);fclose(f);
 size_t header=0;while(header+4<size&&memcmp(data.data()+header,"\0\0\1\xb8",4))header++;
 std::vector<size_t> starts={0};for(size_t i=0;i+6<size;i++)if(!memcmp(data.data()+i,"\0\0\1\0",4)&&((data[i+5]>>3)&7)==1)starts.push_back(i);
 unsigned cases=0;
 for(size_t start:starts){
  unsigned preroll=start?((data[start+4]<<2)|(data[start+5]>>6)):0;
  std::vector<uint64_t> baseline;
  for(unsigned fail: {0u,1u,2u,3u,7u,16u,50u}){
   mpeg2dec_t*d=mpeg2_init();assert(d);mpeg2_buffer(d,data.data(),data.data()+header);while(mpeg2_parse(d)!=STATE_BUFFER){}
   if(fail)mpeg2_skip(d,1);unsigned count=0;bool recovered=false;
   for(size_t pos=start;pos<data.size();pos+=12288){uint8_t*begin=data.data()+pos;uint8_t*end=data.data()+std::min(data.size(),pos+12288);
    mpeg2_buffer(d,begin,end);
    for(;;){auto state=mpeg2_parse(d);if(state==STATE_BUFFER)break;const auto*i=mpeg2_info(d);if(!frame(state,i))continue;
     ++count;
     if(fail && count==fail+preroll){
      FILE*input=fopen(argv[1],"rb");auto*replacement=mpeg2_replay(input,start,pos,data.data(),header,begin,end,count);fclose(input);assert(replacement);
      assert(mpeg2_getpos(replacement)==mpeg2_getpos(d));mpeg2_close(d);d=replacement;i=mpeg2_info(d);recovered=true;++cases;
     }
     if(!fail)baseline.push_back(hash(i));
     else if(recovered)assert(hash(i)==baseline.at(count-1));
    }
   }
   assert(!fail || count==baseline.size());mpeg2_close(d);
  }
 }
 assert(cases>20);std::cout<<cases<<" software recovery points match all remaining decoded frames byte-for-byte\n";
}
