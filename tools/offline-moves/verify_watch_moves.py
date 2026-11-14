#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Replay the APK's ROM-state selector at Watch Mode input timing, without media."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import random
import subprocess
import time
import moves as move_tools
import android_runner


def check_case(binary, run, args, case):
    game,skill,difficulty,phase,start,delay,mode,detour=case
    log=args.output/('%s-%s-d%d-q%d-%02d-%d-detour%d.log'%(game,skill,difficulty,phase,start,mode,detour))
    with log.open('w') as stream:
        rom=args.rom if args.rom else args.roms/(game+'.zip')
        command=[str(binary.resolve()),str(rom.resolve()),game,skill,format(delay,'.17g'),'3600',str(mode),str(difficulty),str(phase),str(detour),str(args.miss_at)]
        process=run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=120)
    rows=[json.loads(line) for line in log.read_text().splitlines() if line.startswith('{')]
    proof=next((x for x in rows if x['type']=='watch_replay'),{})
    return dict(game=game,skill=skill,difficulty=difficulty,input_phase=phase,start=start,start_delay=delay,mode=mode,detour=detour,detour_applied=proof.get('detour_applied',False),verified=process.returncode==0 and proof.get('verified',False),result=proof,log=log.name)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    inputs=p.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--roms',type=Path)
    inputs.add_argument('--rom',type=Path,help='Single ROM ZIP; requires --game')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--starts',type=int,default=8);p.add_argument('--input-phase',type=int,action='append',choices=range(17));p.add_argument('--include',type=Path,default=move_tools.ROOT.parents[1]/'android/app/jni/arcade_moves.inc');p.add_argument('--android',metavar='SERIAL');p.add_argument('--seed',type=int,default=20261115)
    p.add_argument('--game',action='append',choices=move_tools.rom_tables.LAYOUTS,help='Games to check (default: dle21 and ace)')
    p.add_argument('--mode',type=int,action='append',choices=(0,1,2),help='Limit checks to selected modes')
    p.add_argument('--detour',type=int,action='append',help='Use the other strategy at the Nth differing decision, then resume; 0 is normal play')
    p.add_argument('--miss-at',type=int,default=0,help='Withhold input at the Nth move until one life is lost, then require a complete recovery using bundled rows only')
    p.add_argument('--jobs',type=int,choices=range(1,5),default=1,help='Independent replay processes (default: 1)')
    a=p.parse_args()
    games=list(dict.fromkeys(a.game or ('dle21','ace')))
    if a.rom and (not a.game or len(games)!=1):p.error('--rom requires exactly one --game')
    if not 0<=a.miss_at<=1000:p.error('--miss-at must be 0..1000')
    if not 1<=a.starts<=100:p.error('--starts must be 1..100')
    if a.detour and any(not 0<=n<=1000 for n in a.detour):p.error('--detour must be 0..1000')
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
    source_paths=[move_tools.ROOT/name for name in ('watch_moves.c','rom_routes.c','score_routes.c','score_trial.h','simulation.c','board_adapter.c','offline_board.h','rom_catalog.inc','verify_watch_moves.py')]
    source_paths += [move_tools.ROOT.parents[1]/'android/app/jni'/name for name in ('arcade_move_policy.h','arcade_signature.h','arcade_move_catalog.h')]
    sources={str(path.relative_to(move_tools.ROOT.parents[1])):hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}
    rng=random.Random(a.seed);delays=[0]+[rng.uniform(0,30) for _ in range(a.starts-1)]
    results=[];started=time.monotonic()
    configurations=[(g,s,d) for g in games for d in range(move_tools.rom_tables.difficulty_count(g)) for s in move_tools.rom_tables.skills(g)]
    phases=a.input_phase or (0,8,16)
    modes=a.mode or (0,1,2);detours=a.detour or (0,)
    planned=len(configurations)*a.starts*len(modes)*len(phases)*len(detours)
    cases=[(g,s,d,q,i,delay,m,t) for g,s,d in configurations for q in phases
           for i,delay in enumerate(delays) for m in modes for t in detours]
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        futures=[pool.submit(check_case,binary,run,a,case) for case in cases]
        for future in as_completed(futures):
            row=future.result();results.append(row);proof=row['result']
            report=dict(results=results,backend=backend,include_sha256=include_sha256,source_sha256=sources,seed=a.seed,all_passed=len(results)==planned and all(x['verified'] for x in results),completed=len(results),planned=planned,
                        intentional_miss_at=a.miss_at,
                        detours_requested=sum(x['detour']>0 for x in results),detours_exercised=sum(x['detour_applied'] for x in results),
                        all_scenes_proven=False,wall_seconds=round(time.monotonic()-started,3),
                        method='Packaged ROM-state selector, original CPU/player, IRQ guidance, 8ms controller polling, 17ms SDL input delivery with varied phases, 100ms input holds. Mode 0 tests Off selecting Max score for automation.',
                        limitations='Headless input timing model; not a physical Android device test. No claim of all retry contexts or global optimality.')
            move_tools.atomic_json(a.output/'report.json',report)
            print(row['game'],row['skill'],row['difficulty'],row['input_phase'],row['start'],row['mode'],'detour',row['detour'],'PASS' if row['verified'] else 'FAIL',proof.get('score'),proof.get('moves'),'diverted' if row['detour_applied'] else '',flush=True)
    if not all(x['verified'] for x in results):raise SystemExit(1)

if __name__=='__main__':main()
