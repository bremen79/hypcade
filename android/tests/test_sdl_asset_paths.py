#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check production Android resource routing and unchanged desktop behavior."""
import subprocess,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[2]
code=r'''
#include "src/io/sdl_path.h"
#include <cassert>
#include <fstream>
#include <sys/stat.h>
int main(int,char**argv) {
 chdir(argv[1]); mkdir("games",0700);mkdir("private",0700);
 char cwd[4096];assert(getcwd(cwd,sizeof(cwd)));
 std::string base=cwd;
 chdir("games");
#ifdef __ANDROID__
 assert(sdl_read_path("pics/led0.bmp")=="hypseus/pics/led0.bmp");
 assert(sdl_read_path("fonts/default.ttf")=="hypseus/fonts/default.ttf");
 assert(sdl_read_path("sound/grumble.wav")=="hypseus/sound/grumble.wav.bin");
 assert(sdl_file_path("pics/screenshot.png")==base+"/games/pics/screenshot.png");
 assert(sdl_read_path("media/video.m2v")==base+"/games/media/video.m2v");
 assert(sdl_read_path("pics/../secret")==base+"/games/pics/../secret");
 assert(sdl_read_path("/missing/pics/led0.bmp")=="/missing/pics/led0.bmp");
 mkdir((base+"/private/fonts").c_str(),0700);
 std::ofstream(base+"/private/fonts/default.ttf")<<"private override";
 assert(sdl_read_path("fonts/default.ttf")=="hypseus/fonts/default.ttf");
 mkdir("fonts",0700);std::ofstream("fonts/default.ttf")<<"game override";
 assert(sdl_read_path("fonts/default.ttf")==base+"/games/fonts/default.ttf");
 mkdir("sound",0700);std::ofstream("sound/grumble.wav")<<"game override";
 assert(sdl_read_path("sound/grumble.wav")==base+"/games/sound/grumble.wav");
 assert(sdl_file_path("sound/missing.wav")==base+"/games/sound/missing.wav");
 assert(sdl_read_path("sound/custom.ogg")=="hypseus/sound/custom.ogg");
 assert(sdl_read_path("sound/../missing.wav")==base+"/games/sound/../missing.wav");
 mkdir("scene",0700);chdir("scene");
 assert(sdl_read_path("custom.wav")==base+"/games/scene/custom.wav");
#else
 assert(sdl_read_path("sound/grumble.wav")=="sound/grumble.wav");
 assert(sdl_read_path("fonts/default.ttf")=="fonts/default.ttf");
 assert(sdl_file_path("pics/screenshot.png")=="pics/screenshot.png");
#endif
}
'''
with tempfile.TemporaryDirectory() as tmp:
 d=Path(tmp);(d/'test.cpp').write_text('#include <unistd.h>\n#include <stdlib.h>\n'+code)
 for name,flags in [('android',['-D__ANDROID__']),('desktop',[])]:
  subprocess.run(['c++','-std=c++17','-Wall','-Wextra',*flags,'-I',str(root),str(d/'test.cpp'),'-o',str(d/name)],check=True)
  work=d/(name+'-data');work.mkdir()
  subprocess.run([str(d/name),str(work)],check=True)
print('Android APK fallback, filesystem overrides, write paths, chdir and desktop paths passed')
