#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cross-build production MC and compare every output byte under QEMU user mode.
Requires the pinned Android NDK and qemu-aarch64/qemu-arm (or path overrides).
QEMU validates instructions/correctness, not physical-device performance.
"""
import argparse, pathlib, subprocess, tarfile, tempfile
p=argparse.ArgumentParser()
p.add_argument('--ndk',required=True)
p.add_argument('--qemu-dir',default='/usr/bin')
a=p.parse_args()
root=pathlib.Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='hypseus-neon-') as tmp:
 t=pathlib.Path(tmp)
 with tarfile.open(root/'src/3rdparty/libmpeg2/libmpeg2-master.tgz') as f: f.extractall(t,filter='data')
 src=t/'libmpeg2-master'
 (t/'config.h').write_text('#define HAVE_INTTYPES_H 1\n#define HAVE_STDLIB_H 1\n#define HAVE_STRING_H 1\n#define HAVE_MEMORY_H 1\n#define ATTRIBUTE_ALIGNED_MAX 64\n')
 for abi,target,qemu in [('arm64','aarch64-linux-android26','qemu-aarch64'),('armv7','armv7a-linux-androideabi26','qemu-arm')]:
  cc=str(pathlib.Path(a.ndk)/'toolchains/llvm/prebuilt/linux-x86_64/bin'/ (target+'-clang'))
  flags=[cc,'-DHYPSEUS_DECODER_TEST','-O3','-std=c99','-I'+str(t),'-I'+str(src/'include'),'-I'+str(src/'libmpeg2')]
  obj=t/(abi+'.o')
  subprocess.run(flags+['-Dmpeg2_mc_init=mpeg2_mc_init_portable','-c',str(src/'libmpeg2/motion_comp.c'),'-o',str(obj)],check=True)
  idct=t/(abi+'-idct.o')
  subprocess.run(flags+['-Dmpeg2_idct_init=mpeg2_idct_init_portable','-c',str(src/'libmpeg2/idct.c'),'-o',str(idct)],check=True)
  binary=t/abi
  subprocess.run(flags+(['-mfpu=neon'] if abi=='armv7' else [])+['-static',str(obj),str(idct),str(root/'android/app/jni/mpeg2_idct_neon.c'),str(root/'android/app/jni/mpeg2_motion_dispatch.c'),str(root/'android/app/jni/mpeg2_motion_neon.c'),str(root/'android/tests/mpeg2_motion_test.c'),'-o',str(binary)],check=True)
  print(abi,flush=True)
  subprocess.run([str(pathlib.Path(a.qemu_dir)/qemu),str(binary)],check=True)

  # Decode real I/P/B frame streams through the complete library in both modes.
  common=[str(src/'libmpeg2'/f) for f in ['alloc.c','header.c','decode.c','slice.c','cpu_accel.c','cpu_state.c']]
  scalar=t/(abi+'-scalar')
  accelerated=t/(abi+'-neon')
  driver=str(root/'android/tests/mpeg2_stream_test.c')
  subprocess.run(flags+['-static']+common+[str(src/'libmpeg2/motion_comp.c'),str(src/'libmpeg2/idct.c'),driver,'-o',str(scalar)],check=True)
  subprocess.run(flags+(['-mfpu=neon'] if abi=='armv7' else [])+['-static']+common+[str(obj),str(idct),str(root/'android/app/jni/mpeg2_motion_dispatch.c'),str(root/'android/app/jni/mpeg2_motion_neon.c'),str(root/'android/app/jni/mpeg2_idct_neon.c'),driver,'-o',str(accelerated)],check=True)
  for interlaced in [False,True]:
   media=t/('interlaced.m2v' if interlaced else 'progressive.m2v')
   if not media.exists():
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=720x480:rate=30000/1001','-t','3','-c:v','mpeg2video','-g','15','-bf','2','-q:v','3']+(['-flags','+ildct+ilme','-top','1'] if interlaced else [])+['-f','mpeg2video',str(media)],check=True)
   runner=str(pathlib.Path(a.qemu_dir)/qemu)
   baseline=subprocess.check_output([runner,str(scalar),str(media)])
   result=subprocess.check_output([runner,str(accelerated),str(media)])
   assert baseline==result,(abi,media.name,baseline,result)
   assert int(result.split()[0])==90,result
   print(abi,media.name,'full decoder matches scalar:',result.decode().strip(),flush=True)
