#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Factor every DL1 record policy by its semantic scene-exit cost.

No future values are assumed. The saved coefficients solve the scene for each
exit separately; callers must supply a valid continuation contract. A semantic
exit does not by itself determine the future refresh phase.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

import cine_room_optimality
import rom_controls
import euro_optimality
import euro_tables
import rom_proof
import rom_tables

ROOT = Path(__file__).resolve().parent
FIELDS = ('fewest', 'score_at_fewest', 'highest_score', 'fewest_at_score')
GAMES = (*cine_room_optimality.GAMES, *euro_tables.LAYOUTS)


def factor(graph, terminals):
    if set(terminals) != set(graph['goals']):
        raise ValueError('Every terminal needs an explicit exit identity')
    if any(len(ts) != 1 for actions in graph['actions'] for _, ts in actions):
        raise ValueError('Local stochastic transitions require a separate probability contract')
    result = {}
    for name in sorted(set(terminals.values())):
        conditional = dict(graph, goals=[u for u, key in terminals.items() if key == name])
        result[name] = rom_proof.solve(conditional)
        rom_proof.verify(conditional, result[name])
    return result


def evaluate(coefficients, future):
    if set(coefficients) != set(future):
        raise ValueError('Every exit needs an explicit continuation value')
    for row in future.values():
        if set(row) != set(FIELDS) or not (
                all(type(row[k]) is int for k in FIELDS) or all(row[k] is None for k in FIELDS)):
            raise ValueError('Expected four integer continuation coefficients or four explicit dead values')
    count = len(next(iter(coefficients.values()))['fewest']) if coefficients else 0
    values = {k: [None]*count for k in FIELDS}
    for u in range(count):
        options = [tuple(local[k][u]+future[name][k] for k in FIELDS)
                   for name, local in coefficients.items()
                   if local['fewest'][u] is not None and future[name]['fewest'] is not None]
        if options:
            fewest = min(options, key=lambda v: (v[0], -v[1]))
            score = min(options, key=lambda v: (-v[2], v[3]))
            for k, v in zip(FIELDS, (*fewest[:2], *score[2:])):
                values[k][u] = v
    return values


def ranked(graph, coefficients, future, objective):
    if objective not in ('shortest', 'highest-score'):
        raise ValueError('Unknown strategy objective')
    values = evaluate(coefficients, future)
    rows, unequal = rom_proof.ranked(graph, values, objective)
    if unequal:
        raise ValueError('Local phase branching needs a richer continuation contract')
    return values, rows


def check_numeric_tails(graph, coefficients, terminals):
    """Independent whole-DAG check using actual extra input/reward paths."""
    augmented = dict(states=list(graph['states']), awards=list(graph['awards']),
                     actions=[list(a) for a in graph['actions']], goals=[], deaths=list(graph['deaths']))
    future = {}
    for number, name in enumerate(sorted(coefficients)):
        short, high = (number+1, number*7+3), (number+3, number*7+100)
        future[name] = dict(zip(FIELDS, (short[0], short[1], high[1], high[0])))
        for u, key in terminals.items():
            if key != name:
                continue
            for choice, (moves, score) in enumerate((short, high), 1):
                parent = u
                for step in range(moves):
                    v = len(augmented['states'])
                    augmented['states'].append(('synthetic-tail', name, u, choice, step))
                    augmented['actions'].append([])
                    augmented['awards'].append(score if step == moves-1 else 0)
                    augmented['actions'][parent].append(((choice, 0, v), [v]))
                    parent = v
                augmented['goals'].append(parent)
    actual = rom_proof.solve(augmented)
    expected = evaluate(coefficients, future)
    if any(actual[k][:len(graph['states'])] != expected[k] for k in FIELDS):
        raise ValueError('Exit coefficients differ from independent extended-game solve')
    return len(graph['states'])*4


def export(roms, output):
    output.mkdir(parents=True, exist_ok=True)
    started, cases = time.monotonic(), []
    for game in GAMES:
        euro = game in euro_tables.LAYOUTS
        module = euro_tables if euro else rom_tables
        rom = module.load(roms/(game+'.zip'), game)
        model = (euro_optimality.Model if euro else cine_room_optimality.Model)(rom, game)
        if euro:
            model.verify_room_boundaries()
            graph, removed = model.graph(), []
        else:
            graph, _, removed = rom_controls.simplify_controls(model, model.graph())
        terminals = {}
        for u in graph['goals']:
            state = graph['states'][u]
            effect = (('next',) if state == 0 else ('win',)) if euro else (
                list(model.return_labels)[state[1]] if state[0] == 128 else ('win',))
            terminals[u] = ':'.join(map(str, effect))
        coefficients = factor(graph, terminals)
        zero = {name: dict.fromkeys(FIELDS, 0) for name in coefficients}
        local = rom_proof.solve(graph)
        if evaluate(coefficients, zero) != local:
            raise ValueError('Zero continuation does not reproduce local policy values')
        checks = check_numeric_tails(graph, coefficients, terminals)
        local_policies = {o: module.policies(module.inventory(rom, game), o)
                          for o in ('shortest', 'highest-score')}
        key = (lambda state: state) if euro else (lambda state: tuple(state))
        comparison, _ = rom_controls.compare_rankings(graph, local, local_policies, key, euro=euro)
        records = []
        for u, state in enumerate(graph['states']):
            by_exit = {name: {k: values[k][u] for k in FIELDS}
                       for name, values in coefficients.items() if values['fewest'][u] is not None}
            alternatives = []
            for label, (v,) in graph['actions'][u]:
                branches = {}
                for name, values in coefficients.items():
                    if values['fewest'][v] is None:
                        continue
                    branches[name] = dict(fewest=int(bool(label[0]))+values['fewest'][v],
                        score_at_fewest=graph['awards'][u]+values['score_at_fewest'][v],
                        highest_score=graph['awards'][u]+values['highest_score'][v],
                        fewest_at_score=int(bool(label[0]))+values['fewest_at_score'][v])
                alternatives.append(dict(label=label, target=v, local_values_by_exit=branches,
                                         safe_completion=bool(branches)))
            records.append(dict(id=u, record=state, local_values_by_exit=by_exit,
                                common_exit=next(iter(by_exit)) if len(by_exit) == 1 else None,
                                alternatives=alternatives, no_safe_completion=not by_exit))
        data = dict(schema=1, game=game, rom_sha256=hashlib.sha256(rom).hexdigest(),
                    runtime_ready=False, timing='Live ROM descriptor lookup by scene/step or Euro record ID; no calibrated frames',
                    cost='Local per-exit value + supplied exit continuation value',
                    future_contract='Caller must prove each supplied exit value independent of the internal path and timing; semantic exit identity alone does not prove this',
                    fields=FIELDS, terminals=terminals, records=records,
                    excluded_controls=removed, comparison_with_zero_future=comparison,
                    complete_inventory_sha256=hashlib.sha256(json.dumps(module.inventory(rom, game), sort_keys=True).encode()).hexdigest())
        path = output/(game+'-exit-values.json')
        path.write_text(json.dumps(data, separators=(',', ':'))+'\n')
        case = dict(game=game, states=len(records), boundary_classes=sorted(coefficients),
                    common_exit_states=sum(bool(r['common_exit']) for r in records),
                    multiple_exit_states=sum(len(r['local_values_by_exit']) > 1 for r in records),
                    no_safe_completion_states=sum(r['no_safe_completion'] for r in records),
                    independent_extended_game_value_checks=checks,
                    primary_policy_losses={o: c['primary_losses'] for o, c in comparison.items()},
                    secondary_policy_losses={o: c['secondary_losses'] for o, c in comparison.items()},
                    values_file=path.name, values_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        cases.append(case)
        print(json.dumps(case), flush=True)
    report = dict(all_passed=True, cases=cases, seconds=time.monotonic()-started,
                  peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  sources={n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in
                           ('dl1_exit_strategies.py', 'cine_room_optimality.py', 'euro_optimality.py',
                            'rom_controls.py', 'rom_proof.py', 'rom_tables.py', 'euro_tables.py')},
                  scope='Complete per-record semantic exit coefficients for nine DL1 ROMs, including off-policy states. Conditional future-cost representation, not a physical phase policy or APK bundle.')
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--roms', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    export(a.roms, a.output)
