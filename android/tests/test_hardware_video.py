#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the production MediaCodec reader on a connected device, compare seek images
with libmpeg2. Only generated media and a temporary /data/local/tmp directory are
used; no installed apps, settings or user game files are changed. Requires an ARMv7
Android device with a usable MPEG-2 hardware decoder (the primary cabinet target).
"""
import argparse,os,pathlib,struct,subprocess,tarfile,tempfile,uuid
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--serial',required=True);p.add_argument('--sdk',type=pathlib.Path,required=True)
p.add_argument('--ndk',type=pathlib.Path,required=True);p.add_argument('--jdk',type=pathlib.Path,required=True)
a=p.parse_args();root=pathlib.Path(__file__).resolve().parents[2]
adb=[str(a.sdk/'platform-tools/adb'),'-s',a.serial]
remote='/data/local/tmp/hypcade-video-test-'+uuid.uuid4().hex
with tempfile.TemporaryDirectory(prefix='hypcade-hardware-') as tmp:
 d=pathlib.Path(tmp);env=dict(os.environ,JAVA_HOME=str(a.jdk))
 def run(cmd,**kw):return subprocess.run(list(map(str,cmd)),check=True,env=env,**kw)
 jar=a.sdk/'platforms/android-36/android.jar'
 run([a.jdk/'bin/javac','-cp',jar,'-d',d,root/'android/tests/HardwareVideoProbe.java',
      root/'android/app/src/main/java/org/hypseus/android/Mpeg2HardwareDecoder.java',
      root/'android/app/src/main/java/org/hypseus/android/Mpeg2PacketReader.java'])
 run([a.sdk/'build-tools/35.0.0/d8','--min-api','25','--lib',jar,'--output',d]+list(d.rglob('*.class')))
 cc=a.ndk/'toolchains/llvm/prebuilt/linux-x86_64/bin/armv7a-linux-androideabi25-clang++'
 run([cc,'-O3','-std=c++11','-D_FILE_OFFSET_BITS=64','-shared','-fPIC','-static-libstdc++',
      root/'android/app/jni/mpeg2_packets.cpp','-o',d/'packets.so'])
 with tarfile.open(root/'src/3rdparty/libmpeg2/libmpeg2-master.tgz') as t:t.extractall(d,filter='data')
 src=d/'libmpeg2-master'
 (d/'config.h').write_text('#define HAVE_INTTYPES_H 1\n#define HAVE_STDLIB_H 1\n#define HAVE_STRING_H 1\n#define HAVE_MEMORY_H 1\n#define ATTRIBUTE_ALIGNED_MAX 64\n')
 run(['cc','-O2','-I'+str(d),'-I'+str(src/'include'),'-I'+str(src/'libmpeg2')]+[
     src/'libmpeg2'/(name+'.c') for name in ['alloc','header','decode','slice','motion_comp','idct','cpu_accel','cpu_state']]+[
     root/'android/tests/mpeg2_hardware_reference.c','-o',d/'reference'])
 run(adb+['shell','mkdir',remote])
 try:
  for name in ['classes.dex','packets.so']:run(adb+['push',d/name,remote+'/'+name],stdout=subprocess.DEVNULL)
  for interlaced in [False,True]:
   media=d/'video.m2v'
   run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=720x480:rate=30000/1001',
        '-frames:v','90','-c:v','mpeg2video','-g','12','-bf','2','-q:v','4']+
       (['-flags','+ildct+ilme','-top','1'] if interlaced else [])+['-f','mpeg2video',media])
   raw=media.read_bytes();offsets=[0]+[i for i in range(len(raw)-6) if raw[i:i+4]==b'\0\0\1\0' and ((raw[i+5]>>3)&7)==1]
   run([d/'reference',media,d/'reference.bin']+list(map(str,offsets)))
   run(adb+['push',media,remote+'/video.m2v'],stdout=subprocess.DEVNULL)
   run(adb+['shell','CLASSPATH='+remote+'/classes.dex','app_process','/','HardwareVideoProbe',
            remote+'/packets.so',remote+'/video.m2v',remote+'/frames.bin']+list(map(str,offsets)))
   run(adb+['pull',remote+'/frames.bin',d/'hardware.bin'],stdout=subprocess.DEVNULL)
   def records(path):
    data=path.read_bytes();size=12+45*30;assert len(data)%size==0
    return {struct.unpack('>QI',data[i:i+12]):data[i+12:i+size] for i in range(0,len(data),size)}
   software,hardware=records(d/'reference.bin'),records(d/'hardware.bin');worst=0
   for offset in offsets:
    preroll=((raw[offset+4]<<2)|(raw[offset+5]>>6)) if offset else 0
    available=sum(k[0]==offset for k in software)-preroll
    assert sum(k[0]==offset for k in hardware)==min(10,available)
    for frame in range(min(10,available)):
     expected,actual=software[offset,frame+preroll],hardware[offset,frame]
     diff=[abs(x-y) for x,y in zip(expected,actual)];mean=sum(diff)/len(diff)
     assert mean<0.05 and max(diff)<=2,(offset,frame,mean,max(diff))
     worst=max(worst,mean)
   print(('interlaced' if interlaced else 'progressive'),len(hardware),'hardware seek frames match libmpeg2; max mean error',worst,flush=True)
 finally:
  run(adb+['shell','rm','-f']+[remote+'/'+n for n in ['classes.dex','packets.so','video.m2v','frames.bin']])
  run(adb+['shell','rmdir',remote])
