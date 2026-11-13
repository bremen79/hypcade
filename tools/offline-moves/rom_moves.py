#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Extract ROM step graphs, execute both policies, and independently replay wins."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import time
from types import SimpleNamespace

import moves as move_tools
import export_rom_moves
import rom_tables
import score_routes

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]


def identity():
    result=score_routes.source_identity()
    for name in ('rom_tables.py','rom_routes.c','rom_moves.py','export_rom_moves.py','moves.py'):
        p=ROOT/name;result[str(p.relative_to(REPO))]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def build(folder):
    folder.mkdir(parents=True,exist_ok=True);binary=folder/'rom-routes';stamp=folder/'sources.json';tag=identity()
    if binary.exists() and stamp.exists() and json.loads(stamp.read_text())==tag:return binary
    move_tools.verify_vendor();src=ROOT/'vendor/src';staged=folder/'rom-routes.staged'
    print('[build] ROM table player; original CPU and player; no video/audio/waits',flush=True)
    subprocess.run([os.environ.get('CC','cc'),'-O3','-std=c11','-D_POSIX_C_SOURCE=200809L',
                    '-Wall','-Wextra','-Werror','-I'+str(src),str(ROOT/'rom_routes.c'),
                    *[str(src/p) for p in move_tools.SOURCES],'-lz','-lm','-o',str(staged)],check=True)
    if identity()!=tag:raise ValueError('Sources changed during build')
    staged.replace(binary);move_tools.atomic_json(stamp,tag);return binary


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.startswith('{')]


def run(args):
    args.output=args.output.resolve();args.rom=args.rom.resolve();args.output.mkdir(parents=True,exist_ok=True)
    sources=identity();rom_identity=move_tools.identity(args.rom,args.game)
    started=time.monotonic()
    rules=getattr(args,'rules',None)
    if rules:
        package=export_rom_moves.verify(rules,args.rom)
        if package['game']!=args.game:raise ValueError('Export is for a different game')
        data=json.loads((rules/'inventory.json').read_text())
    else:
        data=rom_tables.inventory(rom_tables.load(args.rom,args.game),args.game)
    move_tools.atomic_json(args.output/'inventory.json',data)
    if data['unresolved_targets']:raise ValueError('ROM graph contains unresolved targets')
    for objective in ('shortest','highest-score'):
        policy=rom_tables.policies(data,objective)
        rom_tables.write_policy(args.output/(objective+'.policy'),policy)
        move_tools.atomic_json(args.output/(objective+'-policy.json'),policy)
    print('[ROM] %s: %d unique step records; %d listed transitions; structural parse %.3fs' %
          (args.game,len(data['records']),len(data['edges']),time.monotonic()-started),flush=True)
    binary=build(args.build_dir.resolve());verifier=score_routes.build()
    skills=args.skill or (['ace'] if args.game=='dle21' else ['cadet','captain','ace'])
    rng=random.Random(args.seed);delays=[0]+[rng.uniform(0,30) for _ in range(args.starts-1)]
    report=dict(game=args.game,method='ROM tables plus natural CPU/player execution and independent exact replay',
                sources=sources,rom_chips=rom_identity,results=[],unique_step_records=len(data['records']),
                listed_transitions=len(data['edges']),all_scenes_proven=False,global_optimum_proven=False,
                limits='Policies optimize local table paths to scene exits; original ROM controls scene order, skills and context. Static classification and replayed paths do not validate every alternative or all reachable contexts.')
    visited=set()
    for skill in skills:
        for start,delay in enumerate(delays):
            for objective in ('shortest','highest-score'):
                folder=args.output/(skill+'-%02d'%start)/objective;folder.mkdir(parents=True,exist_ok=True)
                trace=folder/'route.trace';log=folder/'play.jsonl';err=folder/'play.log'
                command=[str(binary),str(args.rom),args.game,skill,format(delay,'.17g'),
                         str(args.output/(objective+'.policy')),str(trace),'3600']
                wall=time.monotonic()
                with log.open('w') as out,err.open('w') as error:
                    result=subprocess.run(command,stdout=out,stderr=error,timeout=120)
                rows=records(log);proof=next((r for r in reversed(rows) if r['type']=='rom_play'),{})
                row=dict(skill=skill,start=start,start_delay=delay,objective=objective,
                         wall_seconds=round(time.monotonic()-wall,4),returncode=result.returncode,play=proof,verified=False)
                for move in rows:
                    if move['type']=='rom_move':visited.add((move['scene'],move['step']))
                if result.returncode==0:
                    native=SimpleNamespace(rom=args.rom,game=args.game,skill=skill,start_delay=delay,max_seconds=3600)
                    verifylog=folder/'replay.log'
                    with verifylog.open('w') as out:
                        checked=subprocess.run(score_routes.command(verifier,native)+['--replay',str(trace)],
                                               stdout=out,stderr=subprocess.STDOUT,timeout=120)
                    replay=records(verifylog);verification=next((r for r in replay if r['type']=='replay'),{})
                    row['verified']=checked.returncode==0 and verification.get('verified',False)
                    row['replay']=verification
                    if row['verified']:
                        moves=[{k:v for k,v in r.items() if k not in ('type','source_step')} for r in replay if r['type']=='replay_move']
                        artifact=dict(schema=4,game=args.game,rom_chips=rom_identity,objective=objective,
                                      configuration=dict(skill=skill,start_delay=delay,max_seconds=3600),
                                      generator_sha256=sources,complete=True,no_life_loss=True,
                                      final_score=verification['score'],move_count=len(moves),
                                      moves=moves,replay=verification,global_optimum_proven=False)
                        move_tools.atomic_json(folder/'route.json',artifact)
                report['results'].append(row);report['visited_action_steps']=[list(x) for x in sorted(visited)]
                report['wall_seconds']=round(time.monotonic()-started,3)
                report['verified_runs']=sum(r['verified'] for r in report['results'])
                report['failed_runs']=len(report['results'])-report['verified_runs']
                move_tools.atomic_json(args.output/'report.json',report)
                print('[%s %s start %d] %s score=%s moves=%s trials=%s %.2fs' %
                      (args.game,skill,start,objective+' VERIFIED' if row['verified'] else objective+' FAILED',
                       proof.get('score'),proof.get('moves'),proof.get('trials'),row['wall_seconds']),flush=True)
    if identity()!=sources:raise ValueError('Sources changed during execution; results retain their original identity')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--game',choices=rom_tables.LAYOUTS,required=True)
    p.add_argument('--rom',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--rules',type=Path,help='Verify and use a complete export_rom_moves.py package')
    p.add_argument('--skill',action='append',choices=('cadet','captain','ace'))
    p.add_argument('--starts',type=int,default=8);p.add_argument('--seed',type=int,default=20261112)
    p.add_argument('--build-dir',type=Path,default=REPO/'local-tools/rom-table-build');a=p.parse_args()
    if not 1<=a.starts<=100:p.error('--starts must be 1..100')
    if a.game=='dle21' and a.skill and a.skill!=['ace']:p.error('DLE21 has no skill selection; use ace placeholder or omit --skill')
    result=run(a)
    if result['failed_runs']:raise SystemExit(1)

if __name__=='__main__':main()
