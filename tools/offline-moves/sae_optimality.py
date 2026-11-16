#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Certify a death-free accepted-command lower bound for SAE 1.0.

This is an optimistic ROM relaxation, not a CPU-state search. See SAE-PROOF.md
for its containment assumptions and the separate executable upper-bound witness.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import time

import rom_tables
import rom_proof

SKILLS = ('cadet', 'captain', 'ace')


class Model:
    def __init__(self, rom, skill):
        self.rom = rom
        self.skill = skill
        self.cache = {}
        pointer = self.word(0x260B + 2 * SKILLS.index(skill))
        self.queue = []
        while rom[pointer] != 255:
            self.queue.append(rom[pointer] & 127)
            pointer += 1

    def word(self, address):
        return rom_tables.word(self.rom, address)

    def record(self, scene, step):
        key = scene, step
        if key not in self.cache:
            # Follow the actual two pointer reads, without inferring table ends
            # from neighboring roots or using the sampled/runtime move bundle.
            table = self.word(0x2571 + 2 * scene)
            self.cache[key] = rom_tables.decode_record(
                self.rom, self.word(table + 2 * step), 'sae')
        return self.cache[key]

    def physical(self, episode):
        if not 1 <= episode <= 40:
            raise ValueError('Unmodeled episode')
        descriptor = 0x2413 + 4 * episode
        pointer = self.word(descriptor)
        flags = self.rom[descriptor + 2]
        count = 2 if flags & 7 and not flags & 8 else 1
        choices = self.rom[pointer:pointer + count]
        if len(choices) != count or any(not x & 128 for x in choices):
            raise ValueError('Invalid physical selector')
        return [x & 127 for x in choices]

    def successors(self, state):
        episode, scene, step, cursor = state
        record = self.record(scene, step)
        if record['system'] or record['trailer'][4] & (4 | 8 | 32 | 64):
            raise ValueError('Unmodeled system/replay effect')
        if record['death'] or record['scene_exit']:
            if record['inputs']:
                raise ValueError('Terminal/death record has input alternatives')
            return []
        choices = [(0, record['trailer'][1])]
        # Include ALL descriptors, even diagonals, zero-length windows and
        # controls unsupported by the current player. Timing is unrestricted.
        for entry in record['inputs']:
            choices.extend((1, window['outcome']) for window in entry['windows'])
        result = []
        for cost, outcome in choices:
            result.extend((target, cost) for target in self.targets(state, outcome))
        return result

    def targets(self, state, outcome):
        episode, scene, step, cursor = state
        if outcome == 255:  # rejected/ignored input: dominated by free wait
            return []
        if not outcome & 128:
            return [(episode, scene, outcome, cursor)]
        if self.record(scene, step)['trailer'][4] & 2:
            following, next_cursor = outcome & 127, cursor
        else:
            if cursor >= len(self.queue):
                raise ValueError('Initial queue exhausted before ending')
            following, next_cursor = self.queue[cursor], cursor + 1
        return [(following, physical, 0, next_cursor) for physical in self.physical(following)]

    def graph(self):
        start = (1, 1, 0, 0)
        nodes = [start]
        index = {start: 0}
        edges, goals = [], []
        for state in nodes:
            source = index[state]
            record = self.record(state[1], state[2])
            if record['scene_exit']:
                # Fail closed if an alternative end appears. SAE's reachable
                # death-free closure has exactly this successful end record.
                if state[1:3] != (25, 63):
                    raise ValueError('Unclassified terminal')
                goals.append(source)
            for target, cost in self.successors(state):
                if target not in index:
                    index[target] = len(nodes)
                    nodes.append(target)
                edges.append((source, index[target], cost))
        check_fresh_episodes(nodes, edges)
        if len(goals) != 1:
            raise ValueError('Expected one successful terminal')
        return nodes, edges, goals


def check_fresh_episodes(nodes, edges):
    """Prove that the first-entry selector suffices, without history masks.

    Work on an overapproximation: union all physical branches within each
    (episode, queue cursor). Every path in it must visit each episode at most
    once. Therefore a first revisit cannot exist in the concrete execution.
    """
    macros = {(s[0], s[3]) for s in nodes}
    next_nodes = {m: set() for m in macros}
    for source, target, _ in edges:
        a, b = nodes[source], nodes[target]
        u, v = (a[0], a[3]), (b[0], b[3])
        if u != v:
            next_nodes[u].add(v)
        elif a[1] != b[1] or (a[2] != 0 and b[2] == 0):
            raise ValueError('Possible same-episode reentry')
    incoming = collections.Counter(v for values in next_nodes.values() for v in values)
    ready = collections.deque(m for m in macros if not incoming[m])
    ancestors = {m: set() for m in macros}
    visited = 0
    while ready:
        u = ready.popleft()
        visited += 1
        if u[0] in ancestors[u]:
            raise ValueError('Possible episode revisit')
        for v in next_nodes[u]:
            ancestors[v].update(ancestors[u] | {u[0]})
            incoming[v] -= 1
            if not incoming[v]:
                ready.append(v)
    if visited != len(macros):
        raise ValueError('Episode scheduler is cyclic')


def boundary_graph(nodes, edges, goals):
    actions = [[] for _ in nodes]
    for source, target, cost in edges:
        actions[source].append(((cost, 0, target), [target]))
    return dict(states=nodes, actions=actions, awards=[0] * len(nodes), goals=goals, deaths=[])


def lower_bound(nodes, edges, goals):
    graph = boundary_graph(nodes, edges, goals)
    distances = rom_proof.solve(graph)['fewest']
    if distances[0] is None:
        raise ValueError('No route to the successful end')
    bound = distances[0]
    # Capping unreachable states at the root bound gives a finite potential.
    return bound, [min(bound, bound if d is None else d) for d in distances]


def verify_potential(edges, goals, potential, bound):
    if not potential or potential[0] != bound or any(type(x) is not int or x < 0 for x in potential):
        raise ValueError('Invalid root/potential')
    if any(potential[g] != 0 for g in goals):
        raise ValueError('Nonzero goal potential')
    for source, target, cost in edges:
        if potential[source] > cost + potential[target]:
            raise ValueError('Bellman inequality violated')


def certify(rom, skill):
    model = Model(rom, skill)
    nodes, edges, goals = model.graph()
    bound, potential = lower_bound(nodes, edges, goals)
    verify_potential(edges, goals, potential, bound)
    return dict(skill=skill, queue=model.queue, lower_bound=bound,
                states=nodes, edges=edges, goals=goals, potential=potential)


def write_policy(rom, skill, path):
    """Rank supported commands globally, keeping Nature adversarial.

    This constructs an upper-bound candidate. Only an original-ROM replay can
    establish that its selected windows are actually executable.
    """
    model = Model(rom, skill)
    nodes, edges, goals = model.graph()
    dag = rom_proof.decision_dag(boundary_graph(nodes, edges, goals))
    values = {}

    def ranked(state):
        rec = model.record(state[1], state[2])
        choices = [(0, 0, rec['trailer'][1])]
        for entry in rec['inputs']:
            if entry['control'] is not None:
                choices.extend((entry['control'], entry['slot'] * 3 + w['window'], w['outcome'])
                               for w in entry['windows'] if w['ticks'])
        result = []
        for control, window, outcome in choices:
            targets = model.targets(state, outcome)
            tails = [values.get(target) for target in targets]
            if not tails or any(tail is None for tail in tails):
                continue
            # Compare (fewest commands, highest guaranteed score as tie-break).
            tail = max(tails)
            total = tail[0] + bool(control), tail[1] - rec['award']
            result.append((total, control, window, outcome))
        return sorted(result)

    # Destinations precede sources; dead ends retain None. No recursion or
    # active-stack cycle handling is needed after validating the DAG.
    for u in dag['order']:
        state = nodes[u]
        rec = model.record(state[1], state[2])
        if rec['scene_exit']:
            values[state] = 0, -rec['award']
        else:
            choices = ranked(state)
            values[state] = choices[0][0] if choices else None
    root = values.get(nodes[0])
    if root is None:
        raise ValueError('No supported surviving policy from the start')
    rows = {}
    for state in nodes:
        rec = model.record(state[1], state[2])
        if rec['death'] or rec['scene_exit']:
            continue
        choices = [(control, window, outcome) for _, control, window, outcome in ranked(state)]
        key = state[1:3]
        if key in rows and rows[key] != choices:
            raise ValueError('Policy needs queue context at runtime')
        rows[key] = choices
    lines = ['HYPCADE_ROM_POLICY_V1']
    for (scene, step), choices in sorted(rows.items()):
        for rank, (control, window, outcome) in enumerate(choices):
            lines.append('%d %d %d %d %d %d' % (scene, step, control, window, outcome, rank))
    path.write_text('\n'.join(lines) + '\n')
    return dict(worst_case_structural_moves=root[0], guaranteed_structural_score=-root[1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify', action='store_true', help='Reconstruct graph and verify saved certificates')
    args = parser.parse_args()
    started = time.monotonic()
    rom = rom_tables.load(args.rom, 'sae')
    digest = hashlib.sha256(rom).hexdigest()
    if args.verify:
        saved = json.loads(args.output.read_text())
        if saved['rom_sha256'] != digest:
            raise ValueError('ROM fingerprint mismatch')
        if len(saved['results']) != len(SKILLS):
            raise ValueError('Incomplete skill coverage')
    results = []
    for i, skill in enumerate(SKILLS):
        row = certify(rom, skill)
        if args.verify:
            old = saved['results'][i]
            for field in ('skill', 'queue', 'states', 'edges', 'goals'):
                if json.loads(json.dumps(row[field])) != old[field]:
                    raise ValueError('Saved graph differs from complete ROM closure')
            verify_potential(row['edges'], row['goals'], old['potential'], old['lower_bound'])
            if row['lower_bound'] != old['lower_bound']:
                raise ValueError('Saved bound differs from solved bound')
        results.append(row)
        print('%s: lower bound %d accepted commands; %d states, %d edges' %
              (skill, row['lower_bound'], len(row['states']), len(row['edges'])))
    if not args.verify:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(dict(schema=1, game='sae', rom_sha256=digest,
            scope='Death-free completion; accepted gameplay commands; optimistic random choices and timing',
            results=results), separators=(',', ':')) + '\n')
    print('%.4f seconds' % (time.monotonic() - started))


if __name__ == '__main__':
    main()
