#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""One SAE rule-transcription, original-ROM validation and DAG-export command.

Checks short routines against the pinned original Z80. No media, Android,
whole-CPU-state search, implicit random probabilities or gameplay timing claims.
"""
import argparse
import collections
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import resource
import time

import rom_kernel
import rom_proof
import rom_tables
from rom_rules import Alternative, Decision, Origin, Reward
from sae_rules import RULES, REFRESH, SaeRules, SaeGraph, SKILLS


def same_ram(expected, actual, label):
    # The standalone CPU calls own their synthetic stack. Everything below
    # that stack, including scratch RAM and aliased bytes, must match exactly.
    differences = [(hex(0xA000 + i), a, b) for i, (a, b) in enumerate(zip(expected, actual))
                   if a != b and i < 0x3D0]
    if differences:
        raise ValueError('%s: transcription/ROM RAM mismatch: %r' % (label, differences[:8]))


def refresh_value(info):
    reads = [(pc, value) for pc, value in info['observations'] if pc == REFRESH.origin.pc]
    if len(reads) > 1:
        raise ValueError('Unexpected multiple selector reads in a boundary routine')
    return reads[0][1] if reads else None


def validate_routines(rom, kernel):
    rules = SaeRules(rom)
    cases = collections.Counter()
    # 1707–171D selects a fixed doubled award using the footer's low nibble.
    # SAE's 1BD7 -> 094A patch adds it atomically, unlike an incremental
    # timing bonus. Check both the suppression gate and multi-byte carries.
    for rank in range(16):
        award = 2 * rom_tables.word(rom, 0x2503 + 2 * rank)
        expected = rules.configured_memory()
        expected.write(0xA200, rank)
        actual, _ = kernel.call(expected.ram, 0x1707, stop=0x171E)
        expected.put_word(0xA013, award)
        same_ram(expected.ram, actual, 'fixed score load')
        cases['fixed_score_load'] += 1
        for disabled in (0, 2):
            expected = rules.configured_memory()
            expected.write(0xA00A, disabled)
            expected.put_word(0xA013, award)
            baseline = 0x12FFFE
            for i in range(3):
                expected.write(0xA032 + i, baseline >> (8 * i))
            adding = not disabled and bool(award & 255)
            actual, _ = kernel.call(expected.ram, 0x1BD7, stop=0x1BEF if adding else 0xDEAD)
            if adding:
                for i in range(3):
                    expected.write(0xA032 + i, (baseline + award) >> (8 * i))
            same_ram(expected.ram, actual, 'fixed score transfer')
            cases['fixed_score_transfer'] += 1
    for skill in SKILLS:
        r = SaeRules(rom, skill)
        expected = r.configured_memory()
        actual, _ = kernel.call(expected.ram, RULES['initial_queue'].pc)
        r.initial_queue(expected)
        same_ram(expected.ram, actual, 'initial_queue ' + skill)
        cases['initial_queue'] += 1
    # Exhaust the actual eight-bit outcome domain, not sampled winning edges.
    for outcome in range(256):
        expected = rules.configured_memory()
        expected.write(0xA012, outcome)
        expected.write(0xA202, 141)
        expected.write(0xA008, 255)
        actual, _ = kernel.call(expected.ram, RULES['outcome'].pc)
        rules.apply_outcome(expected)
        same_ram(expected.ram, actual, 'outcome %d' % outcome)
        cases['outcome'] += 1
        for cursor in range(3):
            for effects in (0, 2, 130):
                expected = rules.configured_memory()
                rules.initial_queue(expected)
                expected.write(0xA012, outcome)
                expected.write(0xA202, 141)
                expected.write(0xA205, effects)
                expected.put_word(0xA0D0, 0xA080 + cursor)
                actual, _ = kernel.call(expected.ram, RULES['queue_or_explicit'].pc)
                rules.next_episode(expected)
                same_ram(expected.ram, actual, 'queue_or_explicit')
                cases['queue_or_explicit'] += 1
    for episode in range(1, 41):
        for history in range(256):
            for seed in (0, 1):
                expected = rules.configured_memory()
                rules.initial_queue(expected)
                expected.write(0xA012, episode | 128)
                expected.write(0xA060 + episode, history)
                expected.write(0xA035, 8 | 32)
                actual, info = kernel.call(expected.ram, RULES['selector'].pc, refresh=seed)
                observations = rules.select_episode(expected, refresh_value(info))
                same_ram(expected.ram, actual, 'selector ep=%d history=%d' % (episode, history))
                if bool(observations) != bool(info['observations']):
                    raise ValueError('Transcription hid or invented a refresh read')
                cases['selector'] += 1
    for bank_gate, death_gate, outcome in ((8, 0, 129), (0, 128, 129), (0, 0, 0), (0, 0, 127)):
        expected = rules.configured_memory()
        expected.bits(0xA010, set_bits=bank_gate)
        expected.write(0xA035, death_gate)
        expected.write(0xA012, outcome)
        actual, _ = kernel.call(expected.ram, RULES['selector'].pc)
        rules.select_episode(expected)
        same_ram(expected.ram, actual, 'selector gate')
        cases['selector_gates'] += 1
    for difficulty in (0, 1):
        r = SaeRules(rom, 'ace', difficulty)
        for count in range(256):
            for flag in (0, 16):
                for outcome in (0, 128):
                    expected = r.configured_memory()
                    expected.write(0xA0D5, count)
                    expected.write(0xA035, flag)
                    expected.write(0xA012, outcome)
                    actual, _ = kernel.call(expected.ram, RULES['progress'].pc)
                    r.progress(expected)
                    same_ram(expected.ram, actual, 'progress')
                    cases['progress'] += 1
    return dict(cases)


def native_step(rules, kernel, ram, outcome, recovery, seed, header=None):
    before = rules.memory(ram)
    record = rules.record(before.read(0xA00E) & 127, before.read(0xA00F))
    rules.install_record(before, record)
    if recovery:
        # Original death prologue, including SAE's score-suppression patch.
        actual, _ = kernel.call(before.ram, 0x0956)
        before = rules.memory(actual)
        before.bits(0xA035, set_bits=128)
        before.write(0xA012, record.scene | 128)
        before.write(0xA00F, 0)
        actual, info = kernel.call(before.ram, 0x1465, stop=0x1492, refresh=seed)
    else:
        if header is not None and header & 16:
            actual, _ = kernel.call(before.ram, 0x095F, stop=0x0964)
            before = rules.memory(actual)
        before.write(0xA012, outcome)
        actual, _ = kernel.call(before.ram, 0x1C8C)
        actual, info = kernel.call(actual, 0x14C9, stop=0x1492, refresh=seed)
    # Verify the original normalized footer loader, not a second Python
    # decoder. IY+2 is the active scene supplied by the loader's caller.
    target = rules.record(actual[14] & 127, actual[15])
    actual[0x202] = target.scene | 128
    actual, _ = kernel.call(actual, 0x166E, stop=0x16D4,
                            hl=target.end - 7 - len(target.extension), ix=0xA200)
    return actual, refresh_value(info)


def validate_graph(model, graph, kernel):
    rules = model.rules
    cases, recoveries = 0, 0
    for point, actions in zip(graph['states'], graph['actions']):
        record = rules.record(point.scene, point.step)
        recovery = record.death
        by_label = {w.label: w.header for w in record.windows}
        choices = [(0, 0, None)] if recovery else sorted({
            (label[2], label[0], by_label.get(tuple(label)) if label[0] else None)
            for label, targets in actions if targets}, key=repr)
        ram = model.materialize(point)
        for outcome, control, header in choices:
            expected_targets = set(model.successors(point, outcome, control, header=header, recovery=recovery))
            observed = set()
            for seed in (0, 1):
                # Also exercise both values of the discarded revisit flag.
                # Its low-outcome guards return without effect in SAE.
                audit_ram = bytearray(ram)
                if seed:
                    audit_ram[0x35] |= 32
                actual, observation = native_step(rules, kernel, audit_ram, outcome, recovery, seed, header)
                expected = rules.transition(audit_ram, outcome, control=control, header=header,
                                            refresh=observation, recovery=recovery)
                same_ram(expected.ram, actual, 'boundary %r outcome=%d restart=%s' % (point, outcome, recovery))
                projected = model.project(actual)
                if projected not in expected_targets:
                    raise ValueError('Concrete ROM destination omitted by DAG projection')
                observed.add(projected)
                cases += 1
                recoveries += int(recovery)
            if observed != expected_targets:
                raise ValueError('Unexercised projected selector alternative')
    return dict(boundary_cases=cases, restart_cases=recoveries)


def projection_invariants(model, graph, values):
    """Check which histories can be revisited before erasing their values."""
    # Check the complete record graph, including losing branches. Recovery
    # links remain a separate coverage relation and are never chosen actions.
    predecessors = [[] for _ in graph['states']]
    remaining = [0] * len(predecessors)
    for u, choices in enumerate(graph['actions']):
        for label, targets in choices:
            for v in targets:
                predecessors[v].append(u)
                remaining[u] += 1
    leaves = collections.deque(u for u, n in enumerate(remaining) if not n)
    ordered = 0
    while leaves:
        v = leaves.popleft()
        ordered += 1
        for u in predecessors[v]:
            remaining[u] -= 1
            if not remaining[u]:
                leaves.append(u)
    if ordered != len(predecessors):
        raise ValueError('A record cycle remains, including on a losing branch')
    macros = {}
    adjacency = collections.defaultdict(set)
    for point in graph['states']:
        key = point.episode, point.cursor, point.queue
        macros[key] = point.episode
    for point, actions in zip(graph['states'], graph['actions']):
        transitions = [(label[2], [graph['states'][v] for v in targets]) for label, targets in actions]
        if model.rules.record(point.scene, point.step).death:
            if point.checkpoint & 128:
                transitions.append((128, model.successors(point, 0, recovery=True)))
        source = point.episode, point.cursor, point.queue
        for outcome, targets in transitions:
            if not outcome & 128:
                continue
            for target in targets:
                dest = target.episode, target.cursor, target.queue
                adjacency[source].add(dest)
    indegree = collections.Counter(v for targets in adjacency.values() for v in targets)
    ready = collections.deque(sorted((u for u in macros if not indegree[u]), key=repr))
    ancestors = {u: set() for u in macros}
    revisited, processed = set(), 0
    while ready:
        u = ready.popleft()
        processed += 1
        if macros[u] in ancestors[u]:
            revisited.add(macros[u])
        for v in adjacency[u]:
            ancestors[v].update(ancestors[u] | {macros[u]})
            indegree[v] -= 1
            if not indegree[v]:
                ready.append(v)
    if processed != len(macros):
        raise ValueError('Episode projection contains a selector cycle')
    if revisited:
        raise ValueError('Retain non-aliased history: a first episode revisit is possible: %r' % sorted(revisited))
    # First-revisit argument: any execution before its hypothetical first
    # revisit is represented by this fresh-selector macro graph. No path in
    # that overapproximation revisits an episode, so a first revisit cannot
    # occur. Aliased histories are retained as the physical queue bytes.
    for point in graph['states']:
        if model.rules.record(point.scene, point.step).effects & (4 | 8 | 32 | 64):
            raise ValueError('History abstraction omits a completion/replay effect')
    rankings = {}
    unequal = {}
    for objective in ('shortest', 'highest-score'):
        rows, differences = rom_proof.ranked(graph, values, objective)
        unequal[objective] = len(differences)
        contexts = collections.defaultdict(set)
        for point, choices in zip(graph['states'], rows):
            contexts[point.scene, point.step].add(tuple(row[1] for row in choices))
        rankings[objective] = sum(len(v) > 1 for v in contexts.values())
    return dict(selector_macro_states=len(macros), possibly_revisited_episodes=sorted(revisited),
                complete_record_graph_acyclic=True,
                nonaliased_histories_fresh_proven=True, exact_history_projection=True,
                context_dependent_rankings=rankings, unequal_external_branches=unequal,
                qualification='Exact history elimination under boundary contracts; not refresh-phase independence or timing feasibility')


def export_case(folder, model, graph, values, audits):
    rules = model.rules
    tag = '%s-d%d' % (rules.skill, rules.difficulty)
    dag = rom_proof.decision_dag(graph)
    # Typed record metadata retains every raw window, including unranked,
    # zero-length and unsupported-control entries. It never exports ROM bytes.
    records = [asdict(rules.record(*key)) for key in sorted({(s.scene, s.step) for s in graph['states']})]
    index = {point: u for u, point in enumerate(graph['states'])}
    decisions = []
    for u, (point, actions) in enumerate(zip(graph['states'], graph['actions'])):
        record = rules.record(point.scene, point.step)
        by_label = {w.label: w.header for w in record.windows}
        for label, targets in actions:
            alternatives, external = [], None
            for transition in model.resolve(point, label[2], label[0], header=by_label.get(tuple(label)) if label[0] else None):
                observation = None
                if transition.reads:
                    external, observation = transition.reads[0]
                alternatives.append(Alternative(index[model.project(transition.ram)], observation))
            decisions.append(asdict(Decision(u, tuple(label), 'input' if label[0] else 'automatic',
                Reward(int(bool(label[0])), graph['awards'][u]), tuple(alternatives),
                Origin(record.address, 'Decoded record outcome'), external)))
    recovery_edges = [dict(source=index[source], targets=[index[t] for t in targets])
                      for source, targets in model.recoveries]
    artifact = dict(schema=1, model='sae-gameplay-boundaries', skill=rules.skill, difficulty=rules.difficulty,
                    state_fields=['episode', 'scene', 'step', 'cursor', 'checkpoint', 'queue', 'score_suppressed'],
                    external_reads=[asdict(REFRESH)], probability_model=None,
                    input_timing='Raw ROM windows; physical acceptance and phase evolution remain external',
                    reward_convention='Current record award once per path; accepted command costs one; death recovery is coverage only',
                    origins={k: asdict(v) for k, v in RULES.items()}, records=records,
                    decisions=decisions, accidental_recovery_edges=recovery_edges,
                    graph=dict(graph, states=[asdict(s) for s in graph['states']]), potential=values,
                    decision_dag=dag,
                    audits=audits)
    (folder / (tag + '.json')).write_text(json.dumps(artifact, separators=(',', ':')) + '\n')
    return dict(skill=rules.skill, difficulty=rules.difficulty, states=len(graph['states']),
                dag_nodes=len(dag['nodes']), automatic_records_collapsed=len(dag['order']) - len(dag['nodes']),
                minimum_commands_bound=values['fewest'][0], maximum_score_bound=values['highest_score'][0],
                queue_variants=[list(q) for q in sorted({s.queue for s in graph['states']})],
                **audits)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    rom = rom_tables.load(args.rom, 'sae')
    kernel = rom_kernel.Kernel(rom, args.output / 'build')
    wall = time.monotonic()
    routines = validate_routines(rom, kernel)
    routine_seconds = time.monotonic() - wall
    print('Literal rule routines:', routines, flush=True)
    cases = []
    for skill in SKILLS:
        for difficulty in (0, 1):
            model = SaeGraph(SaeRules(rom, skill, difficulty))
            wall = time.monotonic()
            graph = rom_proof.closure(model, model.coverage_seeds())
            graph_seconds = time.monotonic() - wall
            wall = time.monotonic()
            values = rom_proof.solve(graph)
            solve_seconds = time.monotonic() - wall
            audits = dict(original_rom=validate_graph(model, graph, kernel),
                          projection=projection_invariants(model, graph, values))
            row = export_case(args.output, model, graph, values, audits)
            row.update(graph_seconds=graph_seconds, solve_seconds=solve_seconds)
            cases.append(row)
            print('%s d%d: %d records, %d DAG nodes; %d original-ROM boundary cases' %
                  (skill, difficulty, row['states'], row['dag_nodes'], audits['original_rom']['boundary_cases']), flush=True)
    root = Path(__file__).resolve().parent
    sources = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in
               ('rom_rules.py', 'sae_rules.py', 'verify_sae_rules.py', 'rom_kernel.c', 'rom_kernel.py',
                'rom_tables.py', 'rom_proof.py', 'vendor/src/cpu/z80.c')}
    report = dict(all_passed=True, rom_sha256=hashlib.sha256(rom).hexdigest(), sources=sources,
                  literal_routines=routines, cases=cases, seconds=time.monotonic() - started,
                  routine_audit_seconds=routine_seconds,
                  peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  scope='Exact RAM boundary transcriptions under explicit R observations, then an audited timing-relaxed support DAG. No assumption of independent randomness, numerical expectation, or timing-optimal gameplay.')
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
