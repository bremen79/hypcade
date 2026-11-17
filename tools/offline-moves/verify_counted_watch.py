#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Count US DL1 ROM-accepted commands during unassisted Watch and replay.

This adds a read-only opcode observer to a generated host harness. Production
sources, ROM bytes, CPU timing and policy selection are not changed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import moves
import rom_tables
import score_routes
import verify_watch_moves

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
GAMES = tuple('lair_'+c for c in 'abcdef')


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Observer insertion site changed: '+old)
    return source.replace(old, new, 1)


def acceptance_pc(rom):
    # The ROM tests the held input, selects a window, reads its outcome and
    # rejects FF before storing the accepted outcome pointer. Observe that
    # store's opcode fetch; the unsuccessful polling path cannot reach it.
    prefix = bytes.fromhex('3e03a1c602dde5e1856f7efeff28e1')
    at = rom.find(prefix)
    if at < 0 or rom.find(prefix, at+1) >= 0:
        raise ValueError('Accepted-input prefix is not unique')
    pc = at+len(prefix)
    if rom[pc:pc+5] not in (bytes.fromhex('2200a03e01'), bytes.fromhex('225aa03e01')):
        raise ValueError('Unknown accepted-outcome pointer store')
    return pc


def build(folder, pcs):
    folder.mkdir(parents=True, exist_ok=True)
    moves.verify_vendor()
    source = (ROOT/'watch_moves.c').read_text()
    source = replace_once(source, 'static unsigned watch_accepted,',
                          'static unsigned watch_accept_pc=0x1850;\nstatic unsigned watch_accepted,')
    source = replace_once(source, 'if(address==0x1850)++watch_accepted;',
                          'if(address==watch_accept_pc)++watch_accepted;')
    injection = '    if(!ace) {\n        watch_accept_pc=0;\n'
    for game, pc in sorted(pcs.items()):
        if game not in GAMES:
            raise ValueError('Unsupported US profile')
        injection += '        if(!strcmp(g.options.game,"%s"))watch_accept_pc=%u;\n' % (game, pc)
    injection += '''        if(!watch_accept_pc)return 2;
        watch_live=&m;watch_original_read=m.board.cpu.bus.read;m.board.cpu.bus.read=watch_read;
    }
'''
    site = '    const char *physical_replay=getenv("HYPCADE_WATCH_REPLAY");'
    source = replace_once(source, site, injection+site)
    source = replace_once(source, '(!ace || (watch_accepted==accepted && watch_end && end))',
                          '(watch_accepted==accepted && (!ace || (watch_end && end)))')
    generated = folder/'counted-watch.c'
    generated.write_text(source)
    binary = (folder/'counted-watch').resolve()
    vendor = ROOT/'vendor/src'
    subprocess.run([os.environ.get('CC', 'cc'), '-O3', '-std=c11',
        '-D_POSIX_C_SOURCE=200809L', '-Wall', '-Wextra', '-Werror',
        '-I'+str(ROOT), '-I'+str(vendor), str(generated),
        *(str(vendor/p) for p in moves.SOURCES), '-lz', '-lm', '-o', str(binary)], check=True)
    return binary, hashlib.sha256(generated.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--game', choices=GAMES, required=True)
    parser.add_argument('--difficulty', type=int, choices=range(4), required=True)
    parser.add_argument('--mode', type=int, choices=(1, 2), required=True,
                        help='1 = Max score; 2 = Fewest inputs')
    parser.add_argument('--input-phase', type=int, choices=range(17), default=0)
    parser.add_argument('--start-delay', type=float, default=0)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 0 <= args.start_delay <= 60:
        parser.error('--start-delay must be finite and in [0, 60]')
    args.output = args.output.resolve()
    rom = rom_tables.load(args.rom, args.game)
    pc = acceptance_pc(rom)
    binary, generated_hash = build(args.output/'build', {args.game: pc})
    run_args = SimpleNamespace(rom=args.rom, roms=None, output=args.output,
                               android=None, miss_at=0)
    case = (args.game, 'ace', args.difficulty, args.input_phase, 0, args.start_delay, args.mode, 0)
    result = verify_watch_moves.check_case(binary, subprocess.run, run_args, case)
    replay = result.get('independent_replay') or {}
    if not result['verified'] or not replay.get('verified') or (
            result['result']['accepted_commands'] != replay.get('accepted_commands')):
        raise ValueError('Counted Watch/independent replay failed')
    paths = [Path(__file__), ROOT/'watch_moves.c', ROOT/'verify_watch_moves.py',
             REPO/'android/app/jni/arcade_moves.inc']
    sources = score_routes.source_identity() | {
        str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    report = dict(result=result, acceptance_pc=pc, rom_sha256=hashlib.sha256(rom).hexdigest(),
                  observer_sha256=generated_hash, sources=sources,
                  scope='Host-only original-CPU ROM acceptance counting and independent physical replay.')
    (args.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(accepted_commands=result['result']['accepted_commands'],
                          score=result['result']['score'], verified=True)))


if __name__ == '__main__':
    main()
