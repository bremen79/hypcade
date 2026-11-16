#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Complete SAE deviation/retry policies, with explicit selector conditions.

Coverage is ROM-derived. Replays validate execution; they never supply missing
states or alternatives. No probability law or deliberate-death reward is used.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import time

import moves
import rom_moves
import rom_proof
import rom_tables
import rom_kernel
from sae_rules import Point, SaeGraph, SaeRules, SKILLS
import verify_sae_rules
import verify_sae_timing


def identity():
    result = verify_sae_timing.identity()
    for name in ('sae_continuations.py', 'verify_sae_rules.py', 'rom_kernel.c', 'rom_kernel.py'):
        p = Path(__file__).with_name(name)
        result[str(p.relative_to(p.parents[2]))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def input_regions(record, ram=None):
    """Exact timer-byte/descriptor priority regions before automatic timeout.

    SAE decrements the first nonzero byte of delay/window[0..2] once per
    game tick. The poller accepts the first matching active descriptor with
    a non-FF outcome. Input windows in a later descriptor can be shadowed.
    With live RAM this also excludes elapsed windows and retains future ones.
    """
    intervals = []
    duration = record.duration if ram is None else int.from_bytes(ram[0x20E:0x210], 'little')
    for window in record.windows:
        if ram is None:
            start, end = window.start_tick, window.end_tick
        else:
            at = 0xE0 + 16 * window.slot
            start = ram[at + 12] + sum(ram[at + 13:at + 13 + window.window])
            end = start + ram[at + 13 + window.window]
        intervals.append((window, start, end))
    cuts = sorted({0, duration, *(t for _, a, b in intervals for t in (a, b) if 0 <= t <= duration)})
    result = []
    for start, end in zip(cuts, cuts[1:]):
        if start >= duration:
            continue
        used = set()
        for window, a, b in intervals:
            if (a <= start < b and window.outcome != 255 and window.control is not None
                    and window.control not in used):
                used.add(window.control)
                result.append(dict(label=window.label, start=start, end=end))
    return result


def audit_inputs(rules, graph, kernel):
    """Original loader, timer and causal input-poller checks at every region.

    Finite routine contracts, not injected full-game start states. Whole-game
    replays below boot normally and retain their actual CPU/IRQ/player clocks.
    """
    cases, ticks, records = 0, 0, 0
    minimum_margin = None
    for scene, step in sorted({(p.scene, p.step) for p in graph['states']}):
        record = rules.record(scene, step)
        if not record.windows:
            continue
        raw = rom_tables.decode_record(rules.rom, record.address, 'sae')
        mem = rules.configured_memory()
        mem.write(0xA00E, scene | 128)
        mem.write(0xA00F, step)
        loaded, _ = kernel.call(mem.ram, 0x15B2, stop=0x16D4)
        footer = 0xA0E0 + 16 * len(raw['inputs'])
        if loaded[footer - 0xA000] != record.flags:
            raise ValueError('Actual loader disagrees about active footer')
        records += 1

        def at_tick(t):
            ram = bytearray(loaded)
            for entry in raw['inputs']:
                at, elapsed = 0xE0 + 16 * entry['slot'], t
                values = [entry['delay_ticks']] + [w['ticks'] for w in entry['windows']]
                for i, value in enumerate(values):
                    ram[at + 12 + i] = max(0, value - elapsed)
                    elapsed = max(0, elapsed - value)
            ram[footer - 0xA000 + 14:footer - 0xA000 + 16] = max(0, record.duration - t).to_bytes(2, 'little')
            return ram

        for region in input_regions(record):
            control, which, outcome = region['label']
            tick = region['start']
            expected = at_tick(tick)
            if tick:
                actual, _ = kernel.call(at_tick(tick - 1), 0x19E9, stop=0x1A2C, iy=footer)
                for entry in raw['inputs']:
                    at = 0xE0 + 16 * entry['slot']
                    if actual[at + 12:at + 16] != expected[at + 12:at + 16]:
                        raise ValueError('Original IRQ timer differs from region arithmetic')
                if actual[footer - 0xA000 + 14:footer - 0xA000 + 16] != expected[footer - 0xA000 + 14:footer - 0xA000 + 16]:
                    raise ValueError('Original IRQ deadline differs from region arithmetic')
                ticks += 1
            actual, info = kernel.call(expected, 0x17DC, stop=0x1850, iy=footer,
                                       input_port=255 ^ control)
            slot, window = divmod(which, 3)
            entry = raw['inputs'][slot]
            pointer = 0xA0E0 + slot * 16 + 2 + ((entry['selector'] >> (2 + 2*window)) & 3)
            if info['a'] != outcome or info['hl'] != pointer or (info['bc'] >> 8) != len(entry['windows']) - window:
                raise ValueError('Original input poller accepted a different control/window/outcome')
            plain, _ = kernel.call(expected, 0x17DC, stop=0x1802, iy=footer, input_port=255)
            flag = 0 if control == 16 else control
            if not actual[0x40 + flag] & 128 or plain[0x40 + flag] & 128:
                raise ValueError('Acceptance is not causal against simultaneous no-input execution')
            cases += 1
            margin = region['end'] - region['start']
            minimum_margin = margin if minimum_margin is None else min(minimum_margin, margin)
    return dict(loader_records=records, causal_window_regions=cases, irq_region_boundaries=ticks,
                minimum_region_ticks=minimum_margin)


class Continuations:
    def __init__(self, rules):
        self.model = SaeGraph(rules)
        self.graph = rom_proof.closure(self.model, self.model.coverage_seeds())
        self.index = {p: i for i, p in enumerate(self.graph['states'])}
        self.recovery = {p: [self.index[t] for t in ts] for p, ts in self.model.recoveries}
        self.regions = {(p.scene, p.step): input_regions(self.model.rules.record(p.scene, p.step))
                        for p in self.graph['states']}
        self.relaxed = rom_proof.solve(self.graph)
        self.graphs = [self.condition(bit) for bit in (0, 1)]
        self.values = [rom_proof.solve(graph) for graph in self.graphs]
        self.rankings = {}
        for objective in ('shortest', 'highest-score'):
            modes = [rom_proof.ranked(g, v, objective)[0] for g, v in zip(self.graphs, self.values)]
            for u, (a, b) in enumerate(zip(*modes)):
                if [row[1] for row in a] != [row[1] for row in b]:
                    raise ValueError('Selector-dependent move ordering at %r' % (self.graph['states'][u],))
            self.rankings[objective] = modes
        # Remove shadowed/zero/expired-at-load windows from executable actions,
        # but preserve every raw alternative in the audit. Prove that this
        # physical restriction changes none of the four conditional values.
        for graph, values in zip(self.graphs, self.values):
            feasible = dict(graph)
            feasible['actions'] = []
            for p, actions in zip(graph['states'], graph['actions']):
                labels = {r['label'] for r in self.regions[p.scene, p.step]}
                feasible['actions'].append([(lab, ts) for lab, ts in actions if not lab[0] or lab in labels])
            if rom_proof.solve(feasible) != values:
                raise ValueError('A conditional bound depends on an unavailable ROM input window')

    def condition(self, bit):
        """Bind episode 40 only. Other selector branches must be value-equal.

        This is a conditional value function, not a claim that an arbitrary
        current physical input schedule can choose its next refresh bit.
        """
        graph = dict(self.graph)
        graph['actions'] = []
        for point, actions in zip(self.graph['states'], self.graph['actions']):
            headers = {w.label: w.header for w in self.model.rules.record(point.scene, point.step).windows}
            choices = []
            for label, targets in actions:
                results = self.model.resolve(point, label[2], label[0], header=headers.get(label))
                if any(r.reads and r.selected_episode == 40 for r in results):
                    targets = sorted({self.index[self.model.project(r.ram)] for r in results
                                      if r.reads[0][1] == bit})
                choices.append((label, targets))
            graph['actions'].append(choices)
        return graph

    def lookup(self, point, objective, *, available=None, selector_bit=None):
        """Rank every legal continuation, optionally excluding expired windows.

        `available` contains ROM labels with an acceptance opportunity remaining,
        including future windows, not merely windows open at this instant. The
        timed executor supplies physical feasibility. An accepted/pending move
        must finish before querying another action.
        """
        if objective not in self.rankings or selector_bit not in (None, 0, 1):
            raise ValueError('Unknown objective/selector condition')
        if point not in self.index:
            raise ValueError('Unrecognized ROM context; do not fall back to a sampled route')
        u = self.index[point]
        recoveries = self.recovery.get(point, [])
        rows = self.rankings[objective][0][u]
        feasible = {r['label'] for r in self.regions[point.scene, point.step]}
        rows = [r for r in rows if not r[1][0] or r[1] in feasible]
        if available is not None:
            allowed = {tuple(label) for label in available}
            rows = [r for r in rows if r[1] in allowed]
        if not rows:
            status = 'goal' if u in self.graph['goals'] else 'await-restart' if recoveries else 'no-surviving-continuation'
            return dict(status=status, actions=[], recovery_targets=recoveries)
        modes = (0, 1) if selector_bit is None else (selector_bit,)
        choices = []
        for _, label, _ in rows:
            conditional = []
            for bit in modes:
                match = next(row for row in self.rankings[objective][bit][u] if row[1] == label)
                if len(set(match[2])) != 1:
                    raise ValueError('An unbound selector still has unequal values')
                conditional.append(dict(selector_bit=bit, value=match[2][0]))
            choices.append(dict(label=label, conditional=conditional))
        return dict(status='play', actions=choices, recovery_targets=[])

    def lookup_live(self, run, objective, selector_bit=None):
        if run._selected is not None or run._pending is not None:
            return dict(status='await-accepted-transition', actions=[])
        point = run._point
        record = self.model.rules.record(point.scene, point.step)
        state = run.state()
        if state.lives == 0:
            return dict(status='game-over', actions=[])
        if record.terminal and (point.scene, point.step) != (25, 63) and state.ram[0x35] & 128:
            return dict(status='await-restart', actions=[])
        regions = input_regions(record, state.ram)
        allowed = [(0, 0, record.default)] + [r['label'] for r in regions]
        result = self.lookup(point, objective, available=allowed, selector_bit=selector_bit)
        if result['actions']:
            best = result['actions'][0]['label']
            result['ready'] = bool(best[0]) and any(r['label'] == best and r['start'] == 0 for r in regions)
        return result

    def export(self, path):
        rows = []
        for u, point in enumerate(self.graph['states']):
            policies = {obj: self.lookup(point, obj) for obj in self.rankings}
            rows.append(dict(point=asdict(point), policies=policies,
                             current_award=self.graph['awards'][u],
                             values=[{key: v[u] for key, v in values.items()} for values in self.values]))
        moves.atomic_json(path, dict(schema=1, skill=self.model.rules.skill, difficulty=self.model.rules.difficulty,
            value_convention='Includes current record award; subtract current_award when queried after the ROM load',
            selector='Episode 40 LD A,R & 1, observed/computed by original CPU; conditions are not probabilities',
            physical_timing='Move order proven in both selector conditions; conditional values do not assert arbitrary-phase attainability',
            states=rows, all_alternatives=self.graph['actions'],
            accidental_recovery=[dict(source=self.index[p], targets=[self.index[t] for t in ts])
                                 for p, ts in self.model.recoveries],
            relaxed_bounds=self.relaxed, conditional_values=self.values))
        return dict(states=len(rows), surviving_states=sum(x is not None for x in self.relaxed['fewest']),
                    recovery_sources=len(self.model.recoveries),
                    score_suppressed_states=sum(p.score_suppressed for p in self.graph['states']),
                    phase_independent_move_rankings=True,
                    all_conditional_bounds_attained_in_admissible_tick_DAG=True,
                    unequal_value_states=sum(any(self.values[0][key][u] != self.values[1][key][u]
                                                for key in self.values[0]) for u in range(len(rows))))


def recovery_case(solution, args, player, objective, kind='recovery'):
    """Withhold one real move, then finish using only the complete policy."""
    rules = solution.model.rules
    tag = '%s-d%d-%s-%s' % (rules.skill, rules.difficulty, objective, kind)
    policy = (args.output / (tag + '.policy')).resolve()
    verify_sae_timing.write_policy(solution.graph, solution.relaxed, objective, policy)
    frontier = verify_sae_timing.timing_frontiers(solution.graph, solution.relaxed, objective)
    attempts = []
    for delay in (0, 4096, 8192, 16384):
        if delay and not frontier['last_input_records']:
            break
        name = tag + '-t%d' % delay
        trace = (args.output / (name + '.trace')).resolve()
        command = [str(player), str(args.rom.resolve()), 'sae', rules.skill, '0', str(policy), str(trace), '3600', str(rules.difficulty)]
        if delay:
            probe = (args.output / (name + '.timing')).resolve()
            probe.write_text('HYPCADE_ROM_TIMING_V1\n' + ''.join('%d %d %d %d\n' % (*r, delay) for r in frontier['last_input_records']))
            command.append(str(probe))
        log = args.output / (name + '.stdout')
        cached = args.reuse_schedules and trace.is_file() and log.is_file()
        if cached:
            returncode = 0
        else:
            env = dict(os.environ)
            env.pop('HYPCADE_ROM_MISS_AT', None)
            env.pop('HYPCADE_ROM_DETOUR_AT', None)
            env['HYPCADE_ROM_MISS_AT' if kind == 'recovery' else 'HYPCADE_ROM_DETOUR_AT'] = str(args.miss_at if kind == 'recovery' else 1)
            with log.open('w') as out, (args.output / (name + '.stderr')).open('w') as err:
                result = subprocess.run(command, env=env, stdout=out, stderr=err, timeout=120)
            returncode = result.returncode
        records = rom_moves.records(log)
        attempts.append(dict(delay=delay, returncode=returncode, reused_schedule=cached))
        if returncode:
            continue
        resume = next((r for r in records if r['type'] == ('rom_resume' if kind == 'recovery' else 'rom_detour')), None)
        if resume is None:
            raise ValueError('Recovery test did not execute a ROM restart')
        checked = verify_sae_timing.replay(rules, args.rom, trace, args.output / 'build', allowed_deaths=int(kind == 'recovery'))
        if kind == 'recovery':
            checkpoint = next(row for row in checked['schedules'] if row['action']['until_cycle'] == resume['cycle'])
            if checkpoint['pending']:
                raise ValueError('Recovery checkpoint contains an outstanding accepted move')
        else:
            accepted = next(e for e in checked['events'] if e['kind'] == 'accepted' and e['cycle'] >= resume['press_cycle']
                            and (e['scene'],e['step'],e['control'],e['outcome']) ==
                            (resume['scene'],resume['step'],resume['control'],resume['outcome']))
            event = next(e for e in checked['events'] if e['kind'] == 'ready' and e['cycle'] > accepted['cycle'])
            checkpoint = dict(point=event['point'], score=event['score'],
                              accepted_commands=sum(e['kind'] == 'accepted' and e['cycle'] < event['cycle'] for e in checked['events']))
        p = dict(checkpoint['point']); p['queue'] = tuple(p['queue']); point = Point(**p)
        u = solution.index[point]
        actual_commands = checked['commands'] - checkpoint['accepted_commands']
        actual_score = checked['score'] - checkpoint['score'] + solution.graph['awards'][u]
        wanted = ((solution.relaxed['fewest'][u], solution.relaxed['score_at_fewest'][u]) if objective == 'shortest' else
                  (solution.relaxed['fewest_at_score'][u], solution.relaxed['highest_score'][u]))
        attained = (actual_commands, actual_score) == wanted
        row = dict(kind=kind, skill=rules.skill, difficulty=rules.difficulty, objective=objective, attempts=attempts.copy(),
                   restart=checkpoint['point'], suffix_commands=actual_commands, suffix_score=actual_score,
                   target=wanted, bound_attained=attained, replay_verified=True,
                   scope='This original-CPU recovery checkpoint, no further deaths')
        moves.atomic_json(args.output / (name + '-replay.json'), checked)
        if attained:
            return row
    return dict(skill=rules.skill, difficulty=rules.difficulty, objective=objective, attempts=attempts,
                bound_attained=False, scope='No bound-attainment certificate; not a proof of suboptimality')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--recovery-matrix', action='store_true')
    parser.add_argument('--deviation-matrix', action='store_true')
    parser.add_argument('--reuse-schedules', action='store_true', help='Treat saved schedules as untrusted witnesses and independently replay them')
    parser.add_argument('--audit-inputs', action='store_true')
    parser.add_argument('--miss-at', type=int, default=12)
    args = parser.parse_args()
    if not 1 <= args.miss_at <= 1000:
        parser.error('--miss-at must be 1..1000')
    args.output.mkdir(parents=True, exist_ok=True)
    sources, started = identity(), time.monotonic()
    rom = rom_tables.load(args.rom, 'sae')
    report = dict(schema=1, rom_sha256=hashlib.sha256(rom).hexdigest(), sources=sources, cases=[], replays=[])
    player = rom_moves.build((args.output / 'build').resolve()) if args.recovery_matrix or args.deviation_matrix else None
    kernel = rom_kernel.Kernel(rom, args.output / 'build') if args.audit_inputs else None
    for skill in SKILLS:
        for difficulty in (0, 1):
            solution = Continuations(SaeRules(rom, skill, difficulty))
            row = solution.export(args.output / ('%s-d%d.json' % (skill, difficulty)))
            row.update(skill=skill, difficulty=difficulty)
            if kernel is not None:
                row['original_input_rules'] = audit_inputs(solution.model.rules, solution.graph, kernel)
            report['cases'].append(row)
            for kind, enabled in (('recovery', args.recovery_matrix), ('deviation', args.deviation_matrix)):
                if not enabled:
                    continue
                for objective in ('shortest', 'highest-score'):
                    case = recovery_case(solution, args, player, objective, kind)
                    report['replays'].append(case)
                    print(skill, difficulty, objective, kind, 'optimum', case['bound_attained'], flush=True)
            report.update(seconds=time.monotonic() - started,
                          peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                          peak_child_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
            moves.atomic_json(args.output / 'report.json', report)
            print(skill, difficulty, row, flush=True)
    if identity() != sources:
        raise ValueError('Sources changed while calculating continuations')
    if (args.recovery_matrix or args.deviation_matrix) and not all(r['bound_attained'] for r in report['replays']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
