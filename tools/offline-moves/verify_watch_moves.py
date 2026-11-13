#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Replay the APK's ROM-state selector at Watch Mode input timing, without media."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import time
import moves as move_tools
import android_runner


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--roms',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--starts',type=int,default=8);p.add_argument('--input-phase',type=int,action='append',choices=range(17));p.add_argument('--include',type=Path,default=move_tools.ROOT.parents[1]/'android/app/jni/arcade_moves.inc');p.add_argument('--android',metavar='SERIAL');p.add_argument('--seed',type=int,default=20261115);a=p.parse_args()
    if not 1<=a.starts<=100:p.error('--starts must be 1..100')
    a.output.mkdir(parents=True,exist_ok=True);src=move_tools.ROOT/'vendor/src';binary=a.output/'watch-moves'
    move_tools.verify_vendor()
    flags=['-DHYPCADE_MOVES_INCLUDE="'+str(a.include.resolve())+'"']
    run=subprocess.run;backend=dict(kind='host')
    if a.android:
        binary=android_runner.compile_android(move_tools.ROOT/'watch_moves.c',binary,flags)
        runner=android_runner.AndroidRunner(a.android,a.output.resolve(),[binary])
        run=runner.run;backend=dict(kind='android',abi=runner.abi,sdk=runner.sdk)
    else:
        subprocess.run(['cc','-O3','-std=c11','-D_POSIX_C_SOURCE=200809L','-Wall','-Wextra','-Werror',*flags,'-I'+str(src),str(move_tools.ROOT/'watch_moves.c'),*[str(src/x) for x in move_tools.SOURCES],'-lz','-lm','-o',str(binary)],check=True)
    include_sha256=hashlib.sha256(a.include.read_bytes()).hexdigest()
    rng=random.Random(a.seed);delays=[0]+[rng.uniform(0,30) for _ in range(a.starts-1)]
    results=[];started=time.monotonic()
    configurations=[('dle21','ace',0)]+[('ace',s,d) for d in range(4) for s in ('cadet','captain','ace')]
    phases=a.input_phase or (0,8,16)
    for game,skill,difficulty,phase in [(g,s,d,q) for g,s,d in configurations for q in phases]:
        for start,delay in enumerate(delays):
            for mode in (0,1,2):
                log=a.output/('%s-%s-d%d-q%d-%02d-%d.log'%(game,skill,difficulty,phase,start,mode))
                with log.open('w') as stream:
                    command=[str(binary.resolve()),str((a.roms/(game+'.zip')).resolve()),game,skill,format(delay,'.17g'),'3600',str(mode),str(difficulty),str(phase)]
                    process=run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=120)
                rows=[json.loads(line) for line in log.read_text().splitlines() if line.startswith('{')]
                proof=next((x for x in rows if x['type']=='watch_replay'),{})
                row=dict(game=game,skill=skill,difficulty=difficulty,input_phase=phase,start=start,start_delay=delay,mode=mode,verified=process.returncode==0 and proof.get('verified',False),result=proof,log=log.name)
                results.append(row)
                report=dict(results=results,backend=backend,include_sha256=include_sha256,seed=a.seed,all_passed=len(results)==len(configurations)*a.starts*3*len(phases) and all(x['verified'] for x in results),completed=len(results),planned=len(configurations)*a.starts*3*len(phases),
                            all_scenes_proven=False,wall_seconds=round(time.monotonic()-started,3),
                            method='Packaged ROM-state selector, original CPU/player, IRQ guidance, 8ms controller polling, 17ms SDL input delivery with varied phases, 100ms input holds. Mode 0 tests Off selecting Max score for automation.',
                            limitations='Headless input timing model; not a physical Android device test. No claim of all retry contexts or global optimality.')
                move_tools.atomic_json(a.output/'report.json',report)
                print(game,skill,difficulty,phase,start,mode,'PASS' if row['verified'] else 'FAIL',proof.get('score'),proof.get('moves'),flush=True)
    if not all(x['verified'] for x in results):raise SystemExit(1)

if __name__=='__main__':main()
