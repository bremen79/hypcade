#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Recompute E/F policy support and certify score/input affine invariants.

Support extrema alone are not attainable ranges. Match them to independent
original-ROM executions before publishing an endpoint as attained.
"""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import dl1_allocation
import rom_proof
import rom_tables
import verify_cost_runtime

REPO = Path(__file__).resolve().parents[2]


def analyse(roms, bundle):
    support = json.loads((REPO/'tools/offline-moves/proof-inputs/us-selectors.json').read_text())
    results = []
    for game in ('lair_e', 'lair_f'):
        table = json.loads((bundle/(game+'.json')).read_text())
        verify_cost_runtime.same_table(table, verify_cost_runtime.basic_expected(table))
        proof = table['certificate']
        inventory = rom_tables.inventory(rom_tables.load(roms/(game+'.zip'), game), game)
        if json.loads(json.dumps(inventory)) != proof['inventory']:
            raise ValueError('ROM inventory differs from certificate: '+game)
        graph = proof['graph']
        values = rom_proof.solve(graph)
        if values != proof['values']:
            raise ValueError('Independent Bellman solution differs: '+game)
        rom_proof.verify(graph, values)
        case = next(c for c in support['cases'] if c['game'] == game)
        groups = [case['descriptors'][str(i)]['scenes'] for i in range(1, 13)]
        tables = {(t['raw_hard'], t['hard']): {
            (r['used'], r['mask']): [(tuple(v), seed) for v, seed in r['support']]
            for r in t['rows']} for t in case['selector_tables']}
        final = case['descriptors']['13']['scenes'][::-1]
        for objective in ('shortest', 'highest-score'):
            local = dl1_allocation.costs(SimpleNamespace(spec=inventory['layout']), graph, values, objective)
            moves = {s: v[0 if objective == 'shortest' else 1] for s, v in local.items()}
            scores = {s: -v[1 if objective == 'shortest' else 0] for s, v in local.items()}
            for difficulty, normal in enumerate((0, 0, 4, 8)):
                first = [tables[normal == 0, g >= normal] for g in range(12)]
                later = tables[normal == 0, True]

                def extrema(scalar):
                    ends = {}
                    for name, sign in (('min', 1), ('max', -1)):
                        costs = {s: (sign*v, 0) for s, v in scalar.items()}
                        plan = dl1_allocation.allocate_three(
                            groups, first, later, costs, normal, offset=42, boundaries=(0,))
                        dl1_allocation.verify_three(plan, first, later, costs, groups, normal, 42)
                        total = dl1_allocation.add(plan['value'], *(costs[s+42] for s in final))
                        ends[name] = sign*total[0]
                    return ends

                ranges = {'moves': extrema(moves), 'score': extrema(scores)}
                invariant = None
                dm = ranges['moves']['max']-ranges['moves']['min']
                ds = ranges['score']['max']-ranges['score']['min']
                if dm and ds % dm == 0:
                    coefficient = ds//dm
                    residual = extrema({s: scores[s]-coefficient*moves[s] for s in moves})
                    if residual['min'] == residual['max']:
                        invariant = dict(formula='score = coefficient * accepted_commands + constant',
                                         coefficient=coefficient, constant=residual['min'])
                results.append(dict(game=game, difficulty=difficulty, objective=objective,
                                    support=ranges, score_input_invariant=invariant))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--roms', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, default=REPO/'android/moves/strategies')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cases = analyse(args.roms, args.bundle)
    sources = [Path(__file__), *(REPO/'tools/offline-moves'/p for p in
        ('dl1_allocation.py', 'rom_proof.py', 'rom_tables.py', 'verify_cost_runtime.py',
         'cost_runtime.py', 'proof-inputs/us-selectors.json')),
        *(args.bundle/(game+'.json') for game in ('lair_e', 'lair_f'))]
    report = dict(cases=cases, sources={str(p.resolve().relative_to(REPO)):
        hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        scope='ROM-authenticated policy room costs and audited scheduler support. '
              'Scalar extrema need attaining executions; verified affine invariants hold over the entire support.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('Recomputed all E/F scalar extrema and affine invariants; original-ROM attainment remains a separate check.')


if __name__ == '__main__':
    main()
