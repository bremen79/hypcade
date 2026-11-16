#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Replan selector-support allocations after an observed first-pass prefix.

Condition actual selected roots instead of demanding one arbitrary optimal
permutation. Values remain phase-relaxed bounds until physical replay; this
does not turn observed timing samples into selector reachability rules.
"""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

import cine_room_optimality
import dl1_allocation
import dl1_selector
import rom_kernel
import rom_proof
import rom_tables

ROOT = CORE


def condition(tables, prefix, groups, normal_groups, offset, masks=None):
    if masks is not None and (len(masks) != len(prefix) or any(m not in (1, 2, 4) for m in masks)):
        raise ValueError('Expected one observed first-visit history bit per prefix room')
    result = list(tables)
    for g, root in enumerate(prefix):
        roots = [s+(0 if g < normal_groups else offset) for s in groups[g]]
        def matches(choice):
            return (roots[choice] if choice < 3 else 80+choice-3) == root
        table = {key: [(transition, seed) for transition, seed in rows if matches(transition[0])
                      and (masks is None or transition[1] == masks[g])]
                 for key, rows in tables[g].items()}
        if not any(table.values()):
            raise ValueError('Prefix room has no original selector support at group %d' % (g+1))
        result[g] = table
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--game', choices=('lair_a', 'lair_b', 'lair_c', 'lair_d'), required=True)
    p.add_argument('--difficulty', type=int, choices=range(4), required=True)
    p.add_argument('--selectors', type=Path, required=True)
    p.add_argument('--first-rooms', required=True, help='Comma-separated observed first-pass physical rooms')
    p.add_argument('--first-masks', help='Optional actual post-selection history masks; distinguishes aliased physical roots')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    prefix = [int(x) for x in a.first_rooms.split(',')]
    masks = [int(x) for x in a.first_masks.split(',')] if a.first_masks else None
    if not 0 < len(prefix) <= 12:
        raise ValueError('Expected one to twelve first-pass room selections')
    cached = json.loads(a.selectors.read_text())
    for name, expected in cached['sources'].items():
        if hashlib.sha256((source_path(name)).read_bytes()).hexdigest() != expected:
            raise ValueError('Selector evidence source changed: '+name)
    saved = next(c for c in cached['cases'] if c['game'] == a.game)
    rom = rom_tables.load(a.rom, a.game)
    if hashlib.sha256(rom).hexdigest() != saved['rom_sha256']:
        raise ValueError('Selector evidence ROM changed')
    tables = {(t['raw_hard'], t['hard']): {(r['used'], r['mask']):
        [(tuple(v), seed) for v, seed in r['support']] for r in t['rows']} for t in saved['selector_tables']}
    descriptors = {}
    for g in range(1, 14):
        at = dl1_selector.descriptor_base(rom)+4*g
        pointer = rom_tables.word(rom, at)
        descriptors[str(g)] = dict(flags=rom[at+2], mask=rom[at+3], scenes=[s & 127 for s in rom[pointer:pointer+3]])
    groups = [descriptors[str(g)]['scenes'] for g in range(1, 13)]
    normal = (0, 0, 4, 8)[a.difficulty]
    raw = normal == 0
    first = condition([tables[raw, g >= normal] for g in range(12)], prefix, groups, normal, 40, masks)
    later = tables[raw, True]
    model = cine_room_optimality.Model(rom, a.game)
    graph = model.graph()
    values = rom_proof.solve(graph)
    kernel = rom_kernel.Kernel(rom, a.output/'build')
    entry = dict(game=a.game, descriptors=descriptors)
    cases = []
    for objective in ('shortest', 'highest-score'):
        costs = dl1_allocation.costs(model, graph, values, objective)
        result = dl1_allocation.allocate_three(groups, first, later, costs, normal)
        dl1_allocation.verify_three(result, first, later, costs, groups, normal)
        native = dl1_allocation.audit_scheduler(rom, entry, result, normal, kernel)
        final = descriptors['13']['scenes'][::-1]
        total = dl1_allocation.add(result['value'], *(costs[s+40] for s in final))
        actual = [total[0], -total[1]] if objective == 'shortest' else [total[1], -total[0]]
        baseline = next(r for r in saved['results'] if (r['difficulty'], r['objective']) == (a.difficulty, objective))
        cases.append(dict(objective=objective, prefix=prefix, first_masks=masks, bound=actual,
            unconditioned_bound=[baseline['inputs'], baseline['score']], allocation=result, native=native))
        print(a.game, objective, prefix, actual, 'unconditioned', cases[-1]['unconditioned_bound'], flush=True)
    report = dict(game=a.game, difficulty=a.difficulty, cases=cases,
        seconds=time.monotonic()-started, peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        selectors_sha256=hashlib.sha256(a.selectors.read_bytes()).hexdigest(),
        sources={n: hashlib.sha256((source_path(n)).read_bytes()).hexdigest() for n in
            ('dl1_prefix_costs.py', 'dl1_allocation.py', 'dl1_selector.py', 'cine_room_optimality.py',
             'rom_tables.py', 'rom_proof.py', 'rom_kernel.py', 'rom_kernel.c')},
        scope='Original-selector support bounds conditioned on observed first-pass roots; explicit-seed routine replays, not physical phase attainability')
    (a.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
