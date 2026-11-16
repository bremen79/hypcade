#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the loop quotient against original-CPU event traces, without a sweep.

Only the established scene-24 late-delay regime is recognized. Expanding to
other frontiers requires a separate ROM loop/path contract, not a fit alone.
"""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import argparse
import hashlib
import json
from pathlib import Path

from future_roms.rom_phase_classes import LoopClasses

ROOT = CORE


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(path):
    report = json.loads(path.read_text())
    for name, expected in report['sources'].items():
        if digest(source_path(name)) != expected:
            raise ValueError('Native trace source changed: ' + name)
    for name, expected in report['generated_sources'].items():
        if digest(path.parent / name) != expected:
            raise ValueError('Native trace generated source changed: ' + name)
    if (report['game'] not in ('lair_e', 'lair_f') or
            (report['scene'], report['step'], report['difficulty'], report['delay_slot']) != (24, 0, 2, 2)):
        raise ValueError('No established loop contract for this frontier')
    events = report['events']
    if (events['poll_m1'], events['poll_cycles']) != (404, 3268):
        raise ValueError('Released poll no longer matches the ROM loop contract')
    # The first two controls are at initial entry and delay expiry. The
    # remaining events are successive C008 reads in the same released regime.
    rows = report['results'][2:]
    if len(rows) < 9 or len({r['read_pc'] for r in rows}) != 1:
        raise ValueError('Incomplete selector event trace')
    if not all(r['accepted'] and r['read_found'] and not r['life_lost'] for r in rows):
        raise ValueError('Event was not a surviving accepted continuation')
    for left, right in zip(rows, rows[1:]):
        if right['delay_cycles'] - left['delay_cycles'] != 3268:
            raise ValueError('Event sequence left the stable poll regime')
    # Full seven-bit R reconstruction is stronger than fitting selector low3.
    model = LoopClasses(404, 3268, 7, 64, modulus=128)
    base = rows[0]['read_r']
    observed = [(r['read_r'] - base) % 128 for r in rows]
    phases = [p for p in range(64) if
              [model.at(p, n)[1] for n in range(len(rows))] == observed]
    if not phases:
        raise ValueError('ROM instruction events contradict the loop quotient')
    if {r['read_r'] % 8 for r in rows[:9]} != set(range(8)):
        raise ValueError('Nine native events did not cover all selector residues')
    return dict(game=report['game'], trace_sha256=digest(path), events_checked=len(rows),
                compatible_clock_residues=phases, full_refresh_modulus=128,
                first_nine_selector_residues=sorted({r['read_r'] % 8 for r in rows[:9]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = [verify(p) for p in args.trace]
    result = dict(verified=True, traces=rows,
        stable_late_loop=LoopClasses(404, 3268, 7, 64).report(),
        early_loop=LoopClasses(380, 3072, 7, 64).report(),
        sources={n: digest(source_path(n)) for n in ('rom_phase_classes.py', 'verify_rom_phase_classes.py')},
        scope='Conditional stable-loop arithmetic and concrete native traces; no arbitrary-phase reachability proof')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
