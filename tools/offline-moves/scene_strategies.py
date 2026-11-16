#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Recalculate SAE local policies with ROM-derived scene-exit values.

Each local solve consumes only its own scene and previously solved exits.
Whole-game values independently verify the result; they do not supply it.
Runtime rows contain descriptor identity and priorities, never replay times.
"""
import argparse
from collections import defaultdict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import resource
import time

import moves
import rom_tables
import rom_proof
from sae_rules import SaeRules, SKILLS
from sae_continuations import Continuations

ROOT = Path(__file__).resolve().parent
FIELDS = ('local_inputs', 'local_score', 'exit', 'exit_inputs', 'exit_score')


def scene_key(point):
    return point.episode, point.scene, point.cursor, point.queue


def continuation_graphs(solution):
    """Keep cardinal/button choices with a nonempty original-ROM window."""
    return [dict(g, actions=[
        [(label, targets) for label, targets in actions
         if label[0] in (0, 1, 2, 4, 8, 16) and
         (not label[0] or label in {r['label'] for r in solution.regions[point.scene, point.step]})]
        for point, actions in zip(g['states'], g['actions'])]) for g in solution.graphs]


def solve_scenes(graph, key=scene_key):
    blocks = defaultdict(list)
    for u, point in enumerate(graph['states']):
        blocks[key(point)].append(u)
    owner = {u: k for k, nodes in blocks.items() for u in nodes}
    dependencies = {k: set() for k in blocks}
    reverse = defaultdict(set)
    for u, actions in enumerate(graph['actions']):
        for _, targets in actions:
            for v in targets:
                if owner[u] != owner[v]:
                    dependencies[owner[u]].add(owner[v])
                    reverse[owner[v]].add(owner[u])
    ready = [k for k in sorted(blocks) if not dependencies[k]]
    count = len(graph['states'])
    values = {k: [None] * count for k in ('fewest', 'highest_score', 'score_at_fewest', 'fewest_at_score')}
    paths = {o: [None] * count for o in ('shortest', 'highest-score')}
    processed = set()
    for block in ready:
        nodes = blocks[block]
        exits = {v for u in nodes for _, ts in graph['actions'][u] for v in ts if owner[v] != block}
        if not exits <= processed:
            raise ValueError('Scene dependency is not solved')
        tails = {v: {k: a[v] for k, a in values.items()} for v in exits}
        local, parts = rom_tables.solve_scene(graph, nodes, tails)
        for k in values:
            for u, value in local[k].items():
                values[k][u] = value
        for objective in paths:
            for u, part in parts[objective].items():
                paths[objective][u] = tuple(part[k] for k in FIELDS) if part else None
        processed.update(nodes)
        for parent in sorted(reverse[block]):
            dependencies[parent].remove(block)
            if not dependencies[parent]:
                ready.append(parent)
    if len(processed) != count:
        raise ValueError('Scene dependency graph is cyclic; this ROM needs a different decomposition')
    return values, paths, len(blocks)


def part_for(graph, paths, values, objective, u, label, v, key=scene_key):
    if values['fewest'][v] is None:
        return None
    if key(graph['states'][u]) == key(graph['states'][v]):
        part = dict(zip(FIELDS, paths[objective][v]))
    else:
        part = dict(local_inputs=0, local_score=0, exit=v,
                    exit_inputs=values['fewest' if objective == 'shortest' else 'fewest_at_score'][v],
                    exit_score=values['score_at_fewest' if objective == 'shortest' else 'highest_score'][v])
    part['local_inputs'] += int(bool(label[0]))
    part['local_score'] += graph['awards'][u]
    part['remaining_inputs'] = part['local_inputs'] + part['exit_inputs']
    part['remaining_score'] = part['local_score'] + part['exit_score']
    return part


HEADER = '''/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "arcade_move_policy.h"
typedef struct {
    uint16_t state;
    uint8_t gate,slot,window,header,outcome,control;
} SaeExitRule;
#include "sae_policy.inc"
static inline ArcadeMoveSelection sae_exit_select(unsigned strategy,const uint8_t *ram) {
    ArcadeMoveSelection result={0,false,0};
    if(strategy>1)return result;
    const uint16_t *order=strategy?sae_exit_fewest:sae_exit_max;
    size_t count=strategy?sizeof(sae_exit_fewest)/sizeof(*sae_exit_fewest):sizeof(sae_exit_max)/sizeof(*sae_exit_max);
    unsigned state=(ram[14]&127)|((ram[15]&127)<<7),gate=(ram[10]>>1)&1,key=state*2+gate;
    size_t low=0,high=count;
    while(low<high){size_t mid=low+(high-low)/2;const SaeExitRule *r=sae_exit_rules+order[mid];
        if(r->state*2U+r->gate<key)low=mid+1;else high=mid;}
    for(size_t i=low;i<count;i++) {
        const SaeExitRule *r=sae_exit_rules+order[i];
        if(r->state!=state || r->gate!=gate)break;
        if(!r->control)return result;
        const uint8_t *x=ram+0xe0+16*r->slot;unsigned w=r->window;
        if(x[0]!=r->header || w>=(x[1]&3) || !x[13+w] || x[2+((x[1]>>(2+2*w))&3)]!=r->outcome)continue;
        unsigned delay=x[12];for(unsigned j=0;j<w;j++)delay+=x[13+j];
        if(delay>12)return result;
        result.controls=r->control;result.ready=delay==0;
        result.window=((uint64_t)state<<32)|((uint64_t)(r->slot*3+w+1)<<8)|r->outcome;
        return result;
    }
    return result;
}
'''


def generate(rom_path, output):
    output.mkdir(parents=True, exist_ok=True)
    rom = rom_tables.load(rom_path, 'sae')
    sources = {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in
               ('scene_strategies.py', 'rom_tables.py', 'sae_rules.py', 'sae_continuations.py', 'rom_proof.py', 'rom_rules.py')}
    # Preserve the complete decoded inventory, including system/death/ignored
    # windows outside the surviving continuation policy.
    moves.atomic_json(output / 'inventory.json', rom_tables.inventory(rom, 'sae'))
    groups, records, reports = {}, {}, []
    started = time.monotonic()
    for skill in SKILLS:
        for difficulty in (0, 1):
            baseline = Continuations(SaeRules(rom, skill, difficulty))
            # Preserve decoded diagonals in the inventory, while restricting
            # every exported ranking to the arcade's cardinal controls.
            baseline.graphs = continuation_graphs(baseline)
            references = [rom_proof.solve(g) for g in baseline.graphs]
            solved = [solve_scenes(g) for g in baseline.graphs]
            for bit, (values, paths, _) in enumerate(solved):
                if values != references[bit]:
                    raise ValueError('Local exit-cost solve differs from independent whole-game solution')
                rom_proof.verify(baseline.graphs[bit], values)
            proof_graph = dict(baseline.graphs[0], states=[asdict(p) for p in baseline.graphs[0]['states']])
            moves.atomic_json(output/('%s-d%d-proof.json'%(skill,difficulty)),dict(
                game='sae',skill=skill,difficulty=difficulty,graph=proof_graph,
                selector_actions=[g['actions'] for g in baseline.graphs],
                values=[row[0] for row in solved]))
            rankings = {o: [rom_proof.ranked(g, s[0], o)[0] for g, s in zip(baseline.graphs, solved)]
                        for o in ('shortest', 'highest-score')}
            path = output / ('%s-d%d-values.jsonl' % (skill, difficulty))
            with path.with_suffix('.tmp').open('w') as stream:
                stream.write(json.dumps(dict(schema=1, skill=skill, difficulty=difficulty,
                    cost='local_inputs + exit_inputs; score=local_score + exit_score',
                    timing='Live ROM descriptor timers; no calibrated frames',
                    selector='Episode 40 conditions 0/1; not probabilities')) + '\n')
                for u, point in enumerate(baseline.graph['states']):
                    record = baseline.model.rules.record(point.scene, point.step)
                    records[point.scene, point.step] = record
                    phases = []
                    for bit, (values, paths, _) in enumerate(solved):
                        policies = {}
                        for objective in rankings:
                            rows = rankings[objective][bit][u]
                            if [r[1] for r in rows] != [r[1] for r in rankings[objective][0][u]]:
                                raise ValueError('Timing-conditioned local rankings differ')
                            policies[objective] = []
                            for rank, (_, label, _) in enumerate(rows):
                                targets = next(ts for lab, ts in baseline.graphs[bit]['actions'][u] if lab == label)
                                branches = [part_for(baseline.graphs[bit], paths, values, objective, u, label, v) for v in targets]
                                policies[objective].append(dict(label=label, rank=rank, branches=branches))
                            key = point.scene, point.step, point.score_suppressed, objective
                            labels = tuple(r[1] for r in rows)
                            if labels:
                                if key in groups and groups[key] != labels:
                                    raise ValueError('Compact runtime key loses a relevant continuation context')
                                groups[key] = labels
                        phases.append(dict(selector_bit=bit, values={k: a[u] for k, a in values.items()}, policies=policies))
                    stream.write(json.dumps(dict(id=u, point=asdict(point), phases=phases), separators=(',', ':')) + '\n')
            path.with_suffix('.tmp').replace(path)
            reports.append(dict(skill=skill, difficulty=difficulty, states=len(baseline.graph['states']),
                                scene_blocks=solved[0][2], both_conditions_match_global=True))
            print(skill, difficulty, reports[-1], flush=True)
    pool, ordered = set(), {}
    for (scene, step, gate, objective), labels in groups.items():
        windows = {w.label: w for w in records[scene, step].windows}
        rows = []
        for control, which, outcome in labels:
            w = windows.get((control, which, outcome)) if control else None
            row = (scene | step << 7, int(gate), w.slot if w else 0, w.window if w else 0,
                   w.header if w else 0, outcome, control)
            pool.add(row);rows.append(row)
        ordered[scene | step << 7, int(gate), objective] = rows
    pool = sorted(pool)
    if len(pool) > 65536:
        raise ValueError('Runtime policy pool exceeds 16-bit indices')
    indices = {r: i for i, r in enumerate(pool)}
    orders = {o: [indices[r] for key, rows in sorted(ordered.items()) if key[2] == o for r in rows]
              for o in ('shortest', 'highest-score')}
    table = dict(schema=1, timing='live-rom', value_files='*-values.jsonl',
                 fields=['state', 'gate', 'slot', 'window', 'header', 'outcome', 'control'],
                 rules=pool, orders=orders)
    moves.atomic_json(output / 'policy.json', table)
    source = ['// SPDX-License-Identifier: GPL-3.0-or-later', '// Local scene policies with continuation costs; live ROM timing.',
              'static const SaeExitRule sae_exit_rules[] = {']
    source += ['{%s},' % ','.join(map(str, row)) for row in pool]
    source.append('};')
    for objective, name in (('shortest', 'fewest'), ('highest-score', 'max')):
        source.append('static const uint16_t sae_exit_%s[] = {' % name)
        source.extend(','.join(map(str, orders[objective][i:i+16])) + ',' for i in range(0, len(orders[objective]), 16))
        source.append('};')
    (output / 'sae_policy.inc').write_text('\n'.join(source) + '\n')
    (output / 'sae_policy.h').write_text(HEADER)
    if any(hashlib.sha256((ROOT / n).read_bytes()).hexdigest() != value for n, value in sources.items()):
        raise ValueError('Sources changed while generating local scene policies')
    manifest = dict(schema=1, game='sae', sources=sources, rom_sha256=hashlib.sha256(rom).hexdigest(),
                    method='Scene-local DAG solves with solved exit continuation costs', cases=reports,
                    runtime_timing='live-rom', runtime_rules=len(pool), seconds=time.monotonic()-started,
                    runtime_bytes=8*len(pool)+2*sum(map(len, orders.values())),
                    peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    limits='Conditional ROM-state policies; timing-dependent selector steering remains separate',
                    files={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())
                           if p.suffix in ('.jsonl', '.json', '.h', '.inc') and p.name != 'manifest.json'})
    moves.atomic_json(output / 'manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    generate(args.rom, args.output)
