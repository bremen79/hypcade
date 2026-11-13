#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise production index validation and atomic publication without video assets."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
code=r'''
#include "src/vldp/android_index.h"
#include <cassert>
#include <fstream>
static void write_index(const std::string &p, int finished=1, uint64_t offset=0) {
 FILE *f=fopen(p.c_str(),"wb"); assert(f);
 dat_header h{}; h.version=DAT_VERSION; h.finished=finished; h.length=100;
 fwrite(&h,sizeof(h),1,f);fwrite(&offset,8,1,f);fclose(f);
}
int main(int argc,char **argv) {
 std::string root=argv[1], video=root+"/clip.m2v", index=root+"/clip.dat";
 std::ofstream(video)<<std::string(100,'x'); mkdir((root+"/indexes").c_str(),0700);
 assert(!android_video_index_ready(video,root));
 write_index(index);assert(android_video_index_ready(video,root));
 write_index(index,0);assert(!android_video_index_ready(video,root));
 write_index(index,1,100);assert(!android_video_index_ready(video,root));
 write_index(index,1,UINT64_MAX);assert(!android_video_index_ready(video,root));
 write_index(index);std::ofstream(index,std::ios::app)<<'x';assert(!android_video_index_ready(video,root));
 write_index(index);assert(!android_index_file_valid(index,101));
 assert(!android_index_publish(index,[&](char *p){write_index(p,0);return false;}));
 assert(android_video_index_ready(video,root)); // interrupted generation preserved old table
 assert(android_index_publish(index,[&](char *p){write_index(p);return true;}));
 remove(index.c_str());
 auto cache=android_index_cache(video,100,root);write_index(cache);
 assert(android_video_index_ready(video,root)); // read-only folder fallback
 // /proc is unwritable even when this test runs as root.
 assert(!android_index_publish("/proc/hypcade-test.dat",[](char*){assert(false);return true;}));
 assert(android_index_publish(cache,[&](char*p){write_index(p);return true;}));
 for (const auto &name : {index,cache}) remove(name.c_str());
}
'''
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp);(p/'test.cpp').write_text(code)
 subprocess.run(['c++','-std=c++17','-D__ANDROID__','-I',str(root),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),tmp],check=True)
 assert not list(p.glob('*.tmp-*'))
print('Video index validation, truncation, invalid offsets, interrupted publication and fallback passed')
