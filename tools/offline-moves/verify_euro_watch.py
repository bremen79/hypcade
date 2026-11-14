#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the production Java Watch player and Euro/Italian ROMs without video.

Uses the actual JNI publisher and packaged policies, not a replacement start
sequence or recorded inputs. Does not launch an Android emulator.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import euro_moves
import euro_tables
from verify_dl2_watch import driver_method

REPO=euro_moves.REPO


def build(folder,jdk):
    folder.mkdir(parents=True,exist_ok=True)
    euro_moves.build(folder/'base')
    source=(REPO/'src/game/laireuro.cpp').read_text()
    methods='\n\n'.join(driver_method(source,sig).replace('laireuro::','EuroMachine::') for sig in euro_moves.METHODS)
    (folder/'euro_driver.inc').write_text('// Extracted original driver methods; retain source notices.\n'+methods)
    (folder/'euro_player.inc').write_text((folder/'base/euro_player.inc').read_text())
    prefix=(REPO/'tools/offline-moves/euro_routes.cpp').read_text().split('struct Input {')[0]
    prefix=prefix.replace('struct EuroMachine {','struct EuroMachine {\n const char *m_shortgamename="laireuro";void update_android_scoreboard(){};')
    (folder/'euro_machine.inc').write_text(prefix)
    java=folder/'java';java.mkdir(exist_ok=True)
    sources=list((REPO/'android/tests/watch-stubs/android/os').glob('*.java'))
    sources+=list((REPO/'android/tests/watch-stubs/android/util').glob('*.java'))
    sources+=[REPO/'android/tests/watch-stubs/org/hypseus/android/BuildConfig.java',
              REPO/'android/app/src/main/java/org/hypseus/android/WatchModeController.java']
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
    (java/'EuroWatchRunner.java').write_text('''package org.hypseus.android;
import android.os.Handler;
final class EuroWatchMachine {
 static native boolean init(String rom,boolean italian,int level,int mode,int phase,boolean startup);
 static native void advanceTo(long ms);
 static native int status();
 static native String summary();
}
public final class EuroWatchRunner {
 public static void main(String[] args) {
  System.load(args[0]);Handler.reset();
  if(!EuroWatchMachine.init(args[1],Boolean.parseBoolean(args[2]),Integer.parseInt(args[3]),Integer.parseInt(args[4]),Integer.parseInt(args[5]),Boolean.parseBoolean(args[6])))throw new IllegalArgumentException("Invalid configuration");
  WatchModeController controller=new WatchModeController();controller.start();
  long limit=Boolean.parseBoolean(args[6])?180000:3600000;
  for(long now=0;now<=limit && EuroWatchMachine.status()==0;now+=8) {
   EuroWatchMachine.advanceTo(now);Handler.advanceTo(now);
   if(now%1000==0 && now<90000 || now%30000==0)System.out.println(EuroWatchMachine.summary());
  }
  controller.stop();System.out.println(EuroWatchMachine.summary());
  if(EuroWatchMachine.status()!=1)System.exit(1);
 }
}
''')
    classes=folder/'classes';classes.mkdir(exist_ok=True)
    subprocess.run([str(jdk/'bin/javac'),'--release','8','-encoding','UTF-8','-d',str(classes),*map(str,sources),*map(str,java.glob('*.java'))],check=True)
    includes=[folder,REPO/'tools/offline-moves/vendor/src',REPO/'android/app/jni',jdk/'include',jdk/'include/linux']
    objects=[]
    for name in ('cpu/z80.c','ldp/ldp.c'):
        original=REPO/'tools/offline-moves/vendor/src'/name
        obj=folder/(original.stem+'.o');objects.append(obj)
        subprocess.run(['cc','-O3','-std=c11','-fPIC','-I'+str(REPO/'tools/offline-moves/vendor/src'),'-c',str(original),'-o',str(obj)],check=True)
    binary=folder/'libeuro-watch.so'
    subprocess.run(['g++','-O3','-std=c++17','-shared','-fPIC',*['-I'+str(p) for p in includes],
                    str(REPO/'tools/offline-moves/euro_watch_machine.cpp'),str(REPO/'android/app/jni/arcade_guidance.cpp'),
                    *map(str,objects),'-Wl,--no-undefined','-o',str(binary)],check=True)
    return binary,classes


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--roms',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--jdk',type=Path,default=Path(os.environ['JAVA_HOME']) if os.environ.get('JAVA_HOME') else None)
    p.add_argument('--game',action='append',choices=euro_tables.LAYOUTS)
    p.add_argument('--level',action='append',type=int,choices=range(4))
    p.add_argument('--mode',action='append',type=int,choices=(1,2))
    p.add_argument('--input-phase',action='append',type=int,choices=range(17))
    p.add_argument('--startup-only',action='store_true');a=p.parse_args()
    if a.jdk is None:p.error('Set JAVA_HOME or --jdk to the installed JDK 17')
    a.output=a.output.resolve();binary,classes=build(a.output/'build',a.jdk)
    paths=['tools/offline-moves/verify_euro_watch.py','tools/offline-moves/euro_watch_machine.cpp',
           'tools/offline-moves/euro_routes.cpp','src/game/laireuro.cpp','src/ldp-in/vp932.cpp',
           'android/app/src/main/java/org/hypseus/android/WatchModeController.java',
           'android/app/jni/arcade_guidance.cpp','android/app/jni/arcade_guidance.h',
           'android/app/jni/arcade_euro_policy.h','android/app/jni/arcade_euro_moves.inc',
           'android/app/jni/arcade_move_catalog.h','android/app/jni/arcade_move_policy.h',
           'android/app/jni/arcade_moves.inc','tools/offline-moves/euro_moves.py',
           'tools/offline-moves/euro_tables.py','tools/offline-moves/verify_dl2_watch.py',
           'tools/offline-moves/vendor/src/cpu/z80.c','tools/offline-moves/vendor/src/ldp/ldp.c']
    # Fingerprint only the scheduling/logging fixtures actually compiled above;
    # the fake unit-test activity is replaced by JNI and is not used here.
    paths+=sorted(str(x.relative_to(REPO)) for package in ('os','util')
                  for x in (REPO/'android/tests/watch-stubs/android'/package).glob('*.java'))
    paths+=['android/tests/watch-stubs/org/hypseus/android/BuildConfig.java']
    report=dict(backend='host-java-jni',startup_only=a.startup_only,all_passed=False,results=[],
                sources={x:hashlib.sha256((REPO/x).read_bytes()).hexdigest() for x in paths})
    for game in a.game or euro_tables.LAYOUTS:
        rom=a.output/(game+'.bin');rom.write_bytes(euro_tables.load(a.roms/(game+'.zip'),game))
        for level in a.level or range(4):
          for mode in a.mode or (1,2):
            for phase in a.input_phase or (0,8,16):
                log=a.output/(game+'-level%d-mode%d-phase%d.log'%(level,mode,phase));began=time.monotonic()
                with log.open('w') as out:
                    result=subprocess.run([str(a.jdk/'bin/java'),'-cp',str(classes),'org.hypseus.android.EuroWatchRunner',
                        str(binary),str(rom),str(game=='lair_ita').lower(),str(level),str(mode),str(phase),str(a.startup_only).lower()],stdout=out,stderr=subprocess.STDOUT,timeout=180)
                rows=[json.loads(line) for line in log.read_text().splitlines() if line.startswith('{')]
                final=rows[-1] if rows else {}
                verified=result.returncode==0 and final.get('complete') is True and final.get('started') is True and final.get('no_life_loss') is True
                row=dict(game=game,level=level,mode=mode,input_phase=phase,verified=verified,returncode=result.returncode,seconds=round(time.monotonic()-began,3),final=final)
                report['results'].append(row);(a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
                print(json.dumps(row),flush=True)
    report['all_passed']=all(x['verified'] for x in report['results'])
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    if not report['all_passed']:raise SystemExit(1)


if __name__=='__main__':main()
