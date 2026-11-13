#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Production fallback replay must preserve the exact frame and input cursor."""
from pathlib import Path
import subprocess,tarfile,tempfile
root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='hypcade-replay-') as tmp:
 p=Path(tmp)
 with tarfile.open(root/'src/3rdparty/libmpeg2/libmpeg2-master.tgz') as t:t.extractall(p,filter='data')
 src=p/'libmpeg2-master'
 (p/'config.h').write_text('#define HAVE_INTTYPES_H 1\n#define HAVE_STDLIB_H 1\n#define HAVE_STRING_H 1\n#define HAVE_MEMORY_H 1\n#define ATTRIBUTE_ALIGNED_MAX 64\n')
 inc=['-I'+str(p),'-I'+str(src/'include'),'-I'+str(src/'libmpeg2')]
 objects=[]
 for name in ['alloc','header','decode','slice','motion_comp','idct','cpu_accel','cpu_state']:
  obj=p/(name+'.o');objects.append(str(obj))
  subprocess.run(['cc','-O2']+inc+['-c',str(src/'libmpeg2'/(name+'.c')),'-o',str(obj)],check=True)
 binary=p/'replay-test'
 subprocess.run(['c++','-std=c++11','-O2']+inc+['-I'+str(root/'android/app/jni'),str(root/'android/app/jni/mpeg2_replay.cpp'),str(root/'android/tests/mpeg2_replay_test.cpp')]+objects+['-o',str(binary)],check=True)
 for interlaced in [False,True]:
  media=p/('interlaced.m2v' if interlaced else 'progressive.m2v')
  subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=720x480:rate=30000/1001','-frames:v','90','-c:v','mpeg2video','-g','12','-bf','2','-q:v','4']+(['-flags','+ildct+ilme','-top','1'] if interlaced else [])+['-f','mpeg2video',str(media)],check=True)
  subprocess.run([str(binary),str(media)],check=True)
