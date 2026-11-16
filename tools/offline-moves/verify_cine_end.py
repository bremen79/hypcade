#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact DL1 trace replay plus original successful-ROM-handler observation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import cine_room_optimality
import moves
import rom_moves
import rom_tables
import score_routes

ROOT=Path(__file__).resolve().parent


def metadata(rom,game):
    model=cine_room_optimality.Model(rom,game)
    match=rom.find(bytes.fromhex('fdcb006ec2'))
    if match<0:raise ValueError('Unrecognized DL1 main-loop end branch')
    pc=rom_tables.word(rom,match+5)
    frames=sorted({r['trailer'][5]|(r['trailer'][6]<<8) for r in model.inventory['records']
                   if r['address'] in model.winning_addresses})
    if not 1<=len(frames)<=2:raise ValueError('Unclassified successful end frames')
    return pc,frames+[frames[0]]*(2-len(frames))


def build(output):
    output.mkdir(parents=True,exist_ok=True);moves.verify_vendor();vendor=ROOT/'vendor/src'
    binary=output/'cine-end-replay'
    subprocess.run([os.environ.get('CC','cc'),'-O3','-ffp-contract=off','-std=c11',
        '-D_POSIX_C_SOURCE=200809L','-Wall','-Wextra','-Werror','-I'+str(vendor),str(ROOT/'cine_end_replay.c'),
        *[str(vendor/p) for p in moves.SOURCES],'-lz','-lm','-o',str(binary)],check=True)
    return binary.resolve()


def run(args):
    args.output.mkdir(parents=True,exist_ok=True)
    rom=rom_tables.load(args.rom,args.game);pc,frames=metadata(rom,args.game)
    binary=build(args.output/'build')
    env=dict(os.environ,HYPCADE_END_PC=str(pc),HYPCADE_END_FRAME0=str(frames[0]),HYPCADE_END_FRAME1=str(frames[1]))
    with (args.output/'replay.jsonl').open('w') as out,(args.output/'replay.log').open('w') as err:
        completed=subprocess.run([str(binary),str(args.rom.resolve()),args.game,'ace',str(args.start_delay),'3600',
            '--difficulty',str(args.difficulty),'--replay',str(args.trace.resolve())],env=env,stdout=out,stderr=err,timeout=120)
    rows=rom_moves.records(args.output/'replay.jsonl')
    replay=next((r for r in rows if r['type']=='replay'),{})
    end=next((r for r in rows if r['type']=='rom_end'),{})
    report=dict(game=args.game,verified=bool(completed.returncode==0 and replay.get('verified') and end.get('verified')),
                replay=replay,rom_end=end,handler_pc=pc,winning_frames=frames,
                rom_sha256=hashlib.sha256(rom).hexdigest(),trace_sha256=hashlib.sha256(args.trace.read_bytes()).hexdigest(),
                sources=score_routes.source_identity()|{str((ROOT/n).relative_to(ROOT.parents[1])):hashlib.sha256((ROOT/n).read_bytes()).hexdigest()
                                                       for n in ('verify_cine_end.py','cine_end_replay.c','cine_room_optimality.py')},
                scope='Independent exact physical-input replay and original successful end-handler; host only')
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
    if not report['verified']:raise SystemExit(1)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',type=Path,required=True);p.add_argument('--game',choices=cine_room_optimality.GAMES,required=True)
    p.add_argument('--trace',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--difficulty',type=int,default=0,choices=range(4));p.add_argument('--start-delay',type=float,default=0)
    run(p.parse_args())


if __name__=='__main__':main()
