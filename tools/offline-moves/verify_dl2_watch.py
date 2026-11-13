#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the production Java Watch Mode controller and DL2 ROM without video.

The test remaps only Android scheduling imports to a deterministic clock. The
controller body, JNI guidance, i86 CPU, driver ports, EEPROM and Sony protocol
are the production sources. No recorded inputs or hand-written moves are used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import zipfile
import zlib

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]


def driver_method(source,signature):
    start=source.index(signature)
    lexical=re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',lambda m:' '*len(m.group()),source,flags=re.S)
    p=lexical.index('{',start);end=p+1;level=1
    while level:
        level+=(lexical[end]=='{')-(lexical[end]=='}');end+=1
    return source[start:end].replace('lair2::','Dl2Machine::').replace('#ifdef __ANDROID__','#if 1')


def prepare(folder):
    folder.mkdir(parents=True,exist_ok=True)
    source=(REPO/'src/game/lair2.cpp').read_text()
    methods='\n\n'.join(driver_method(source,signature) for signature in (
        'void lair2::port_write','Uint8 lair2::port_read','void lair2::EEPROM_9536_write',
        'void lair2::cpu_mem_write','void lair2::do_irq','void lair2::input_enable','void lair2::input_disable'))
    start=source.index('            // FIX compiler bugs',source.index('case 6: // 319',source.index('void lair2::patch_roms')))
    end=source.index('            break;',start)
    patch=source[start:end].replace('m_cpumem','ram')
    (folder/'dl2_driver.inc').write_text('// Generated from src/game/lair2.cpp; original source and notices remain in the repository.\n'+methods+'\nvoid patch_driver() {\n'+patch+'\n}\n')
    (folder/'config.h').write_text('#define USE_I86 1\n')
    java=folder/'java';java.mkdir(exist_ok=True)
    for package in ('os','util'):
        for original in (REPO/'android/tests/watch-stubs/android'/package).glob('*.java'):
            (java/original.name).write_text(original.read_text().replace('package android.','package org.hypseus.watchtest.android.'))
    controller=REPO/'android/app/src/main/java/org/hypseus/android/WatchModeController.java'
    (java/controller.name).write_text(controller.read_text().replace('import android.','import org.hypseus.watchtest.android.'))
    (java/'BuildConfig.java').write_text((REPO/'android/tests/watch-stubs/org/hypseus/android/BuildConfig.java').read_text())
    (java/'HypseusActivity.java').write_text('''package org.hypseus.android;
final class HypseusActivity {
 static native void nativeArcadeInput(int action,boolean down);
 static native boolean nativeEmulatorReady();
 static native int nativeWatchCredits();
 static native boolean nativeWatchCoinPending();
 static native boolean nativeWatchGameStarted();
 static native void nativeSetWatchAutomation(boolean enabled);
 static native long nativeGuidance();
 static native long nativeTakeWatchMove();
 static native void nativeRequestCurrentWatchMove();
}
''')
    (java/'NativeRomMachine.java').write_text('''package org.hypseus.android;
final class NativeRomMachine {
 static native boolean init(String rom,int level,int seek,int phase,int omit);
 static native void advanceTo(long ms);
 static native int status();
 static native String summary();
}
''')
    (java/'WatchRomRunner.java').write_text('''package org.hypseus.android;
import org.hypseus.watchtest.android.os.Handler;
public final class WatchRomRunner {
 public static void main(String[] args) {
  System.load(args[0]);Handler.reset();
  if(!NativeRomMachine.init(args[1],Integer.parseInt(args[2]),Integer.parseInt(args[3]),Integer.parseInt(args[4]),Integer.parseInt(args[5])))throw new IllegalArgumentException("Invalid ROM/configuration");
  WatchModeController controller=new WatchModeController();controller.start();
  for(long now=0;now<=3600000 && NativeRomMachine.status()==0;now+=8) {
   NativeRomMachine.advanceTo(now);Handler.advanceTo(now);
   if(now%30000==0)System.out.println(NativeRomMachine.summary());
  }
  controller.stop();System.out.println(NativeRomMachine.summary());
  if(NativeRomMachine.status()!=1)System.exit(1);
 }
}
''')
    return java


def build(folder,jdk,android=False):
    java=prepare(folder)
    classes=folder/'classes';classes.mkdir(exist_ok=True)
    subprocess.run([str(jdk/'bin/javac'),'--release','8','-encoding','UTF-8','-d',str(classes),*[str(p) for p in sorted(java.glob('*.java'))]],check=True)
    compiler=os.environ.get('CXX','g++')
    includes=['-I'+str(folder),'-I'+str(REPO/'android/third_party/SDL/include'),'-I'+str(REPO/'src/3rdparty/plog/include')]
    if android:
        sdk=Path(os.environ.get('ANDROID_HOME',Path.home()/'Android/Sdk'))
        compiler=str(sdk/'ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/i686-linux-android25-clang++')
        includes+=['-static-libstdc++']
    else:
        includes+=['-I'+str(jdk/'include'),'-I'+str(jdk/'include/linux')]
    binary=folder/'libdl2-watch.so'
    subprocess.run([compiler,'-O3','-std=c++17','-shared','-fPIC',*includes,
        str(ROOT/'dl2_watch_machine.cpp'),str(REPO/'android/app/jni/arcade_guidance.cpp'),
        str(REPO/'src/io/numstr.cpp'),'-lz','-o',str(binary)],check=True)
    return binary,classes


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--jdk',type=Path,default=Path(os.environ['JAVA_HOME']) if os.environ.get('JAVA_HOME') else None)
    p.add_argument('--android',metavar='SERIAL',help='Run the same Java/JNI test on an Android emulator')
    p.add_argument('--level',type=int,action='append',choices=range(5))
    p.add_argument('--seek-ms',type=int,action='append');p.add_argument('--input-phase',type=int,action='append',choices=range(17))
    p.add_argument('--omit-move',choices=('none','first','final'),default='none',help='Negative control: withhold one input and require a detected death')
    a=p.parse_args()
    if a.jdk is None:
        javac=shutil.which('javac')
        if not javac:p.error('Set JAVA_HOME or pass --jdk for the existing JDK 17 installation')
        a.jdk=Path(javac).resolve().parents[1]
    a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(a.rom) as archive:
        names=[n for n in archive.namelist() if n.lower()=='dl2_319.bin']
        if len(names)!=1:raise ValueError('Supply DL2 US 3.19')
        rom=archive.read(names[0])
    if len(rom)!=65536 or zlib.crc32(rom)!=0xe9453a1b:raise ValueError('Unsupported ROM revision')
    raw=a.output/'dl2_319.bin';raw.write_bytes(rom)
    binary,classes=build(a.output/'build',a.jdk,bool(a.android))
    remote='/data/local/tmp/hypcade-dl2-moves'
    if a.android:
        adb=['adb','-s',a.android]
        abi=subprocess.check_output(adb+['shell','getprop','ro.product.cpu.abi'],text=True).strip()
        if abi!='x86':p.error('This Android test build currently requires an x86 emulator')
        sdk=Path(os.environ.get('ANDROID_HOME',Path.home()/'Android/Sdk'))
        jar=a.output/'build/classes.jar'
        subprocess.run([str(a.jdk/'bin/jar'),'cf',str(jar),'-C',str(classes),'.'],check=True)
        dex=a.output/'build/dex';dex.mkdir(exist_ok=True)
        env=dict(os.environ,JAVA_HOME=str(a.jdk))
        subprocess.run([str(sdk/'build-tools/35.0.0/d8'),'--min-api','25','--lib',str(sdk/'platforms/android-36/android.jar'),'--output',str(dex),str(jar)],env=env,check=True)
        subprocess.run(adb+['shell','mkdir','-p',remote],check=True)
        for file in (binary,raw,dex/'classes.dex'):
            subprocess.run(adb+['push',str(file),remote+'/'+file.name],check=True,stdout=subprocess.DEVNULL)

    sources=[ROOT/'verify_dl2_watch.py',ROOT/'dl2_watch_machine.cpp',
             REPO/'android/app/src/main/java/org/hypseus/android/WatchModeController.java',
             REPO/'android/app/jni/arcade_guidance.cpp',REPO/'android/app/jni/arcade_guidance.h',
             REPO/'android/app/jni/arcade_moves.inc',REPO/'src/game/lair2.cpp',
             REPO/'src/ldp-in/ldp1000.cpp',REPO/'src/io/numstr.cpp']
    sources+=list((REPO/'src/cpu/x86').rglob('*'))
    sources+=list((REPO/'android/tests/watch-stubs').rglob('*.java'))
    identity={str(path.relative_to(REPO)):hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(sources) if path.is_file()}
    levels=a.level or range(5);seeks=a.seek_ms or (0,17,55);phases=a.input_phase or (0,8,16)
    if any(seek<0 for seek in seeks):p.error('--seek-ms must be nonnegative')
    planned=len(levels)*len(seeks)*len(phases)
    omit=('none','first','final').index(a.omit_move)
    report=dict(game='lair2',backend='android-x86' if a.android else 'host',omit_move=a.omit_move,rom_sha256=hashlib.sha256(rom).hexdigest(),
                sources=identity,planned=planned,completed=0,results=[],all_passed=False)
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    for level in levels:
      for seek in seeks:
       for phase in phases:
        log=a.output/('level%d-seek%d-phase%d.log'%(level,seek,phase));began=time.monotonic()
        with log.open('w') as out:
            command=[str(a.jdk/'bin/java'),'-cp',str(classes),'org.hypseus.android.WatchRomRunner',str(binary),str(raw),str(level),str(seek),str(phase),str(omit)]
            if a.android:
                command=adb+['shell','env','CLASSPATH='+remote+'/classes.dex','app_process','/',
                    'org.hypseus.android.WatchRomRunner',remote+'/'+binary.name,remote+'/'+raw.name,str(level),str(seek),str(phase),str(omit)]
            result=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT,timeout=180)
        events=[json.loads(line) for line in log.read_text().splitlines() if line.startswith('{')]
        final=events[-1] if events else {}
        verified=(result.returncode==0 and final.get('complete') is True and final.get('no_life_loss') is True) if not omit else (result.returncode==1 and final.get('complete') is False and final.get('losses',0)>0 and final.get('omitted')==1)
        row=dict(level=level,seek_ms=seek,input_phase=phase,returncode=result.returncode,verified=verified,
                 result=final,wall_seconds=round(time.monotonic()-began,3))
        report['results'].append(row);report['completed']=len(report['results'])
        report['all_passed']=report['completed']==planned and all(r['verified'] for r in report['results'])
        (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(level,seek,phase,'PASS' if row['verified'] else 'FAIL',row['result'],flush=True)
    if not report['all_passed']:raise SystemExit(1)

if __name__=='__main__':main()
