#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Extract European-board moves and run the original European driver without video.

Android execution is deliberately opt-in and is not performed by this tool.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import euro_tables
from verify_dl2_watch import driver_method
import moves

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
METHODS = ('void laireuro::do_irq', 'void laireuro::do_nmi',
    'Uint8 laireuro::cpu_mem_read', 'void laireuro::cpu_mem_write',
    'void laireuro::port_write', 'Uint8 laireuro::port_read',
    'void laireuro::input_enable', 'void laireuro::input_disable',
    'void ctc_write', 'Uint8 ctc_read', 'void dart_write', 'void ctc_init',
    'void ctc_update_period')


def identity():
    paths = ['src/game/laireuro.cpp', 'src/ldp-in/vp932.cpp',
        'android/app/jni/arcade_euro_policy.h', 'android/app/jni/arcade_move_policy.h']
    paths += ['tools/offline-moves/'+name for name in
        ('euro_moves.py', 'euro_tables.py', 'euro_routes.cpp', 'move_arrays.py', 'verify_dl2_watch.py',
         'vendor/src/cpu/z80.c', 'vendor/src/ldp/ldp.c')]
    return {p: hashlib.sha256((REPO/p).read_bytes()).hexdigest() for p in paths}


def build(folder):
    folder.mkdir(parents=True, exist_ok=True)
    sources = identity(); stamp = folder/'sources.json'; binary = folder/'euro-routes'
    if binary.exists() and stamp.exists() and json.loads(stamp.read_text()) == sources:
        return binary
    moves.verify_vendor()
    # The harness publishes the same selector at the end of each 50 Hz tick;
    # avoid linking a second JNI publisher into the extracted desktop methods.
    source = (REPO/'src/game/laireuro.cpp').read_text().replace('#ifdef __ANDROID__', '#if 0')
    methods = '\n\n'.join(driver_method(source, sig).replace('laireuro::', 'EuroMachine::') for sig in METHODS)
    (folder/'euro_driver.inc').write_text('// Generated from src/game/laireuro.cpp; retain original source and notices.\n'+methods+'\n')
    player = (REPO/'src/ldp-in/vp932.cpp').read_text()
    (folder/'euro_player.inc').write_text('// Generated from src/ldp-in/vp932.cpp; retain original source and notices.\n'+player[player.index('namespace vp932\n{'):])
    src = ROOT/'vendor/src'
    for name in ('cpu/z80.c', 'ldp/ldp.c'):
        subprocess.run([os.environ.get('CC', 'cc'), '-O3', '-std=c11', '-I'+str(src),
            '-c', str(src/name), '-o', str(folder/(Path(name).stem+'.o'))], check=True)
    subprocess.run([os.environ.get('CXX', 'g++'), '-O3', '-std=c++17', '-Wall', '-Wextra',
        '-I'+str(src), '-I'+str(folder), '-I'+str(REPO/'android/app/jni'),
        str(ROOT/'euro_routes.cpp'), str(folder/'z80.o'), str(folder/'ldp.o'),
        '-o', str(binary)], check=True)
    if sources != identity():
        raise ValueError('Sources changed during European harness build')
    stamp.write_text(json.dumps(sources, indent=2)+'\n')
    return binary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--game', choices=euro_tables.LAYOUTS, default='lair_ita')
    parser.add_argument('--difficulty', type=int, choices=range(4), help='Native bank-A difficulty; omitted uses the revision factory setting')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--starts', type=int, default=2)
    parser.add_argument('--input-phase', type=int, action='append', choices=range(17))
    parser.add_argument('--miss', type=int, default=0, help='Withhold this numbered move and require recovery after exactly one life loss')
    parser.add_argument('--build-dir', type=Path, default=REPO/'local-tools/euro-moves-build')
    args = parser.parse_args()
    if args.starts < 1:
        parser.error('--starts must be positive')
    out = args.output.resolve(); data, policies = euro_tables.export(args.rom, out, args.game)
    rom = out/'program.bin'; rom.write_bytes(euro_tables.load(args.rom,args.game))
    banks=list(euro_tables.LAYOUTS[args.game]['banks'])
    if args.difficulty is not None:
        banks[0]=(banks[0]&0x3f)|((3-args.difficulty)<<6)
    difficulty=((~banks[0])&255)>>6
    binary = build(args.build_dir.resolve())
    report = dict(game=args.game, sources=identity(), rom_sha256=data['rom_sha256'],
        backend='host-video-less', results=[], android_tested=False,
        difficulty=difficulty,raw_banks=banks,
        planned=args.starts*2*len(args.input_phase or (0,8,16)),
        all_scenes_proven=False, global_optimum_proven=False)
    for start in range(args.starts):
        for goal in policies:
            for phase in args.input_phase or (0, 8, 16):
                name='%s-%d-phase%d' % (goal,start,phase)
                trace=out/(name+'.trace'); wall=time.monotonic()
                command=[str(binary),str(rom),str(out/(goal+'.policy')),str(trace),
                    str(start*11317 % 30001),str(phase),str(args.miss)]
                proofs=[]
                for replay in (0,1):
                    with (out/(name+('-replay' if replay else '')+'.log')).open('w') as err:
                        result=subprocess.run(command+[str(replay),*[str(v) for v in banks],
                            str(int(euro_tables.LAYOUTS[args.game]['per_player_difficulty']))],stdout=subprocess.PIPE,stderr=err,text=True,timeout=120)
                    proof=json.loads(result.stdout);proof['returncode']=result.returncode;proofs.append(proof)
                fields=('score','moves','lives','initial_lives','ms','difficulty')
                verified=all(p.get('win') and p['returncode']==0 for p in proofs) and all(proofs[0].get(k)==proofs[1].get(k) for k in fields)
                row=dict(objective=goal,start=start,start_delay_ms=start*11317 % 30001,phase=phase,miss=args.miss,difficulty=difficulty,
                    verified=verified,proofs=proofs,seconds=round(time.monotonic()-wall,3))
                report['results'].append(row)
                (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
                print('[%s %s start %d phase %d] %s score=%s moves=%s %.3fs' %
                    (args.game,goal,start,phase,'PASS' if verified else 'FAIL',proofs[0].get('score'),proofs[0].get('moves'),row['seconds']),flush=True)
    if any(not r['verified'] for r in report['results']):
        raise SystemExit('European play failed; do not publish')
    if identity()!=report['sources']:
        raise SystemExit('Sources changed during European verification; do not publish')
    if not args.miss:
        euro_tables.write_bundle(out/'bundle',[euro_tables.compact(data,policies)],[report])



if __name__ == '__main__':
    main()
