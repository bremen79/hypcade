#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate ROM-extracted policies across every supported skill/difficulty."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import random
import subprocess
import time
from types import SimpleNamespace

import export_rom_moves
import android_runner
import moves as move_tools
import rom_moves
import score_routes


def check_case(binary, verifier, args, case):
    game, skill, difficulty, start, delay, objective = case
    folder = args.output / game / ('%s-d%d-%02d' % (skill, difficulty, start)) / objective
    folder.mkdir(parents=True)
    trace = folder / 'route.trace'
    rules = args.output / 'rules' / game
    began = time.monotonic()
    command = [str(binary), str((args.roms / (game + '.zip')).resolve()), game, skill,
               format(delay, '.17g'), str((rules / (objective + '.policy')).resolve()),
               str(trace.resolve()), '3600', str(difficulty)]
    with (folder / 'play.jsonl').open('w') as out, (folder / 'play.log').open('w') as err:
        result = args.run_command(command, stdout=out, stderr=err, timeout=args.timeout)
    records = rom_moves.records(folder / 'play.jsonl')
    proof = next((r for r in reversed(records) if r['type'] == 'rom_play'), {})
    row = dict(game=game, skill=skill, difficulty=difficulty, start=start, start_delay=delay,
               objective=objective, directory=str(folder.relative_to(args.output)),
               verified=False, returncode=result.returncode, play=proof)
    if result.returncode == 0:
        options = SimpleNamespace(rom=args.roms / (game + '.zip'), game=game, skill=skill,
                                  difficulty=difficulty, start_delay=delay, max_seconds=3600)
        with (folder / 'replay.log').open('w') as out:
            replay = args.run_command(score_routes.command(verifier, options) + ['--replay', str(trace.resolve())],
                                    stdout=out, stderr=subprocess.STDOUT, timeout=args.timeout)
        events = rom_moves.records(folder / 'replay.log')
        verification = next((r for r in events if r['type'] == 'replay'), {})
        row['replay'] = verification
        row['verified'] = replay.returncode == 0 and verification.get('verified', False)
        if row['verified']:
            accepted = [{k: v for k, v in event.items() if k not in ('type', 'source_step')}
                        for event in events if event['type'] == 'replay_move']
            move_tools.atomic_json(folder / 'route.json', dict(
                schema=5, game=game, rom_chips=move_tools.identity(options.rom, game),
                objective=objective, configuration=dict(skill=skill, difficulty=difficulty,
                    start_delay=delay, max_seconds=3600), generator_sha256=rom_moves.identity(),
                complete=True, no_life_loss=True, final_score=verification['score'],
                move_count=len(accepted), moves=accepted, replay=verification,
                global_optimum_proven=False))
    row['wall_seconds'] = round(time.monotonic() - began, 3)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--roms', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--starts', type=int, default=8)
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--seed', type=int, default=20261114)
    parser.add_argument('--timeout',type=float,default=300,help='Wall seconds per play or replay; virtual time remains capped at one hour')
    parser.add_argument('--android',metavar='SERIAL',help='Run the full check on an x86 Android emulator')
    args = parser.parse_args()
    if not 1 <= args.starts <= 100 or not 1 <= args.jobs <= 4:
        parser.error('--starts must be 1..100; --jobs must be 1..4')
    if not 0<args.timeout<86400:parser.error('--timeout must be positive and less than one day')
    if args.output.exists():
        parser.error('Choose a new output directory')
    args.output = args.output.resolve()
    args.output.mkdir(parents=True)
    for game in ('dle21', 'ace'):
        export_rom_moves.export(args.roms / (game + '.zip'), game, args.output / 'rules' / game)
    binary = rom_moves.build(rom_moves.REPO / 'local-tools/rom-table-build')
    verifier = score_routes.build()
    args.run_command=subprocess.run
    backend=dict(kind='host')
    if args.android:
        build=args.output/'android-build';build.mkdir()
        binary=android_runner.compile_android(rom_moves.ROOT/'rom_routes.c',build/'rom-routes')
        verifier=android_runner.compile_android(rom_moves.ROOT/'score_routes.c',build/'score-routes')
        runner=android_runner.AndroidRunner(args.android,args.output,[binary,verifier])
        args.run_command=runner.run
        backend=dict(kind='android',abi=runner.abi,sdk=runner.sdk)
    sources = rom_moves.identity()
    rng = random.Random(args.seed)
    delays = [0] + [rng.uniform(0, 30) for _ in range(args.starts - 1)]
    cases = [(game, skill, difficulty, start, delay, objective)
             for game in ('dle21', 'ace')
             for difficulty in (range(4) if game == 'ace' else (0,))
             for skill in (('cadet', 'captain', 'ace') if game == 'ace' else ('ace',))
             for start, delay in enumerate(delays)
             for objective in ('shortest', 'highest-score')]
    report = dict(schema=1, sources=sources,backend=backend, results=[], planned=len(cases), completed=0,
                  seed=args.seed, starts=args.starts, all_passed=False,
                  limits='Natural randomized starts, all supported skills/operator difficulties; not proof of every retry context or global optimality.')
    began = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(check_case, binary, verifier, args, case): case for case in cases}
        for future in as_completed(futures):
            try:
                row = future.result()
            except (subprocess.TimeoutExpired,OSError,ValueError) as error:
                game,skill,difficulty,start,delay,objective=futures[future]
                row=dict(game=game,skill=skill,difficulty=difficulty,start=start,start_delay=delay,
                         objective=objective,verified=False,error=str(error),play={},wall_seconds=0)
            report['results'].append(row)
            report['results'].sort(key=lambda r: (r['game'], r['difficulty'], r['skill'], r['start'], r['objective']))
            report['completed'] += 1
            report['verified_runs'] = sum(r['verified'] for r in report['results'])
            report['failed_runs'] = report['completed'] - report['verified_runs']
            report['all_passed'] = report['completed'] == report['planned'] and not report['failed_runs']
            report['wall_seconds'] = round(time.monotonic() - began, 3)
            move_tools.atomic_json(args.output / 'report.json', report)
            print('[%d/%d] %s %s difficulty=%d start=%d %s %s score=%s moves=%s %.2fs' % (
                report['completed'], len(cases), row['game'], row['skill'], row['difficulty'], row['start'],
                row['objective'], 'PASS' if row['verified'] else 'FAIL', row['play'].get('score'),
                row['play'].get('moves'), row['wall_seconds']), flush=True)
    if sources != rom_moves.identity():
        report['all_passed']=False;report['source_changed']=True
        move_tools.atomic_json(args.output/'report.json',report)
        raise ValueError('Sources changed during verification')
    if not report['all_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
