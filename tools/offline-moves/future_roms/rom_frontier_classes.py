#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""ROM-derived timing triage for every optimal cardinal DL1 room input.

Partition by descriptor timer events, preserve all cardinal optimal actions,
and report exact conditional loop classes. No physical timing sweep or room
permutation product is constructed. Nominal decoded timers are deliberately
separate from harder-mode loader transformations and complete IRQ paths.
"""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import resource
import time

import cine_room_optimality
import rom_controls
from future_roms import rom_phase_classes
from future_roms import rom_poll_rules
import rom_proof
import rom_tables
from future_roms import rom_timer_rules
from future_roms import rom_wait_rules

ROOT = CORE


@lru_cache(maxsize=None)
def classes(mp, tp, mw, tw, waiting):
    if not waiting:
        # This only classifies refresh at the input frontier. Following
        # automatic polling/IRQs cannot be treated as a fixed suffix.
        return dict(source_only=True,
            parity=rom_phase_classes.LoopClasses(mp, 0, 0, 1, 2).report(),
            refresh=rom_phase_classes.LoopClasses(mp, 0, 0, 1).report())
    return dict(source_only=False,
        parity=rom_phase_classes.LoopClasses(mp, tp, mw, tw, 2).report(),
        refresh=rom_phase_classes.LoopClasses(mp, tp, mw, tw).report())


def regions(record, game, label):
    duration = record['trailer'][2] | record['trailer'][3] << 8
    initial = [[entry['delay_ticks']] + [w['ticks'] for w in entry['windows']] +
               [0]*(3-len(entry['windows'])) for entry in record['inputs']]
    result = []
    for region in rom_controls.accepted_regions(record):
        if tuple(region['label']) != tuple(label):
            continue
        a, b = region['start'], region['end']
        cuts = sorted({a, b, *([duration-255] if a < duration-255 < b else [])})
        for lo, hi in zip(cuts, cuts[1:]):
            timers, footer = rom_timer_rules.advance(initial, duration, lo)
            desc = [(len(e['windows']), row) for e, row in zip(record['inputs'], timers)]
            poll = rom_poll_rules.cost(game, desc, footer=footer,
                flags=record['trailer'][0], effects=record['trailer'][4])
            slot, window = divmod(label[1], 3)
            entry = record['inputs'][slot]
            waiting = rom_wait_rules.waits_for_descriptor(entry, window)
            active = next((i for i, value in enumerate(timers[slot]) if value), None)
            if active != window+1:
                raise ValueError('Accepted interval and sequential timer state disagree')
            mw = rom_wait_rules.iteration_m1(active) if waiting else 0
            tw = 38+26*active if waiting else 1
            result.append(dict(start_tick=lo, end_tick=hi, poll_m1=poll.m1, poll_cycles=poll.cycles,
                wait=waiting, wait_m1=mw, wait_cycles=tw if waiting else None,
                conditional_classes=classes(poll.m1, poll.cycles, mw, tw, waiting)))
    return result


def analyze(rom, game):
    model = cine_room_optimality.Model(rom, game)
    graph = model.graph()
    graph, values, _ = rom_controls.simplify_controls(model, graph)
    answer = {}
    for objective, cost_key in (('shortest', 'fewest'), ('highest-score', 'fewest_at_score')):
        rankings = rom_proof.ranked(graph, values, objective)[0]
        rows = []
        for u, ranked in enumerate(rankings):
            if not ranked or not values[cost_key][u]:
                continue
            state = graph['states'][u]
            if state[0] == 128:
                continue
            for value, label, _ in ranked:
                if value != ranked[0][0] or not label[0]:
                    continue
                record = model.record(*state)
                intervals = regions(record, game, label)
                if not intervals:
                    raise ValueError('Cardinal optimal input has no nominal interval')
                rows.append(dict(scene=state[0], step=state[1], label=label,
                    optimal_inputs_to_boundary=values[cost_key][u], intervals=intervals))
        answer[objective] = rows
    return dict(game=game, rom_sha256=hashlib.sha256(rom).hexdigest(), objectives=answer,
        scope='Nominal ROM timer intervals at all optimal room inputs. Conditional unchanged-loop classes only; not selector reachability or a harder-loader/IRQ proof.')


def audit_native(rom, result, build):
    """Check both ends of each unique interval with the original routines."""
    game = result['game']
    model = cine_room_optimality.Model(rom, game)
    poll = rom_poll_rules.PollKernel(rom, build/'poll')
    wait = rom_wait_rules.WaitKernel(rom, build/'wait')
    poll_entry = rom_poll_rules.locate(rom)
    wait_entry = rom.find(rom_wait_rules.SIGNATURE)
    if wait_entry < 0:
        raise ValueError('Original accepted-wait routine not found')
    seen = set()
    poll_cases = wait_cases = 0
    for rows in result['objectives'].values():
        for row in rows:
            record = model.record(row['scene'], row['step'])
            initial = [[e['delay_ticks']] + [w['ticks'] for w in e['windows']] +
                       [0]*(3-len(e['windows'])) for e in record['inputs']]
            for interval in row['intervals']:
                for tick in {interval['start_tick'], interval['end_tick']-1}:
                    key = row['scene'], row['step'], tuple(row['label']), tick
                    if key in seen:
                        continue
                    seen.add(key)
                    duration = record['trailer'][2] | record['trailer'][3] << 8
                    timers, footer = rom_timer_rules.advance(initial, duration, tick)
                    desc = [(len(e['windows']), t) for e, t in zip(record['inputs'], timers)]
                    ram, iy = rom_poll_rules.memory(desc, footer,
                        flags=record['trailer'][0], effects=record['trailer'][4])
                    after, regs, _, _ = poll.once(ram, poll_entry, iy, 127)
                    if (regs[3], regs[4]) != (interval['poll_m1'], interval['poll_cycles']):
                        raise ValueError('Native nominal interval poll cost differs')
                    if after[:0x3d0] != ram[:0x3d0] or regs[5]:
                        raise ValueError('Released interval changed RAM or read R')
                    poll_cases += 1
                    if interval['wait']:
                        ram = bytearray(1024)
                        ram[0xec:0xf0] = bytes(timers[row['label'][1]//3])
                        after, (r, pc, _), _, writes = wait.once(ram, wait_entry, 127)
                        if r != (127+interval['wait_m1']) % 128 or pc != wait_entry or after != ram or writes:
                            raise ValueError('Native nominal interval wait differs')
                        wait_cases += 1
    return dict(poll_endpoint_cases=poll_cases, wait_endpoint_cases=wait_cases,
        scope='Original released-poll fixed point and accepted-wait iteration at nominal interval endpoints; no interrupts or harder-loader composition')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--roms', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--audit-native', action='store_true')
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    cases = []
    for game in cine_room_optimality.GAMES:
        rom = rom_tables.load(a.roms/(game+'.zip'), game)
        result = analyze(rom, game)
        if a.audit_native:
            result['native'] = audit_native(rom, result, a.output/'build'/game)
        path = a.output/(game+'.json')
        path.write_text(json.dumps(result, indent=2)+'\n')
        cases.append(dict(game=game, file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            optimal_input_frontiers={o: len(rows) for o, rows in result['objectives'].items()}, native=result.get('native')))
        print(game, cases[-1]['optimal_input_frontiers'], flush=True)
    report = dict(cases=cases, seconds=time.monotonic()-started,
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        sources={n: hashlib.sha256((source_path(n)).read_bytes()).hexdigest() for n in
            ('rom_frontier_classes.py', 'cine_room_optimality.py', 'rom_controls.py', 'rom_tables.py',
             'rom_proof.py', 'rom_phase_classes.py', 'rom_poll_rules.py', 'rom_timer_rules.py', 'rom_wait_rules.py')},
        scope='Seven Cine DL1 revisions, complete cardinal optimal input-frontier inventory; conditional nominal loop contracts only')
    (a.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
