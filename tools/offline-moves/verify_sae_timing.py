#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Replay physical schedules through timed SAE rules, without a policy oracle.

Reconstruct the complete ROM DAG independently. Attainment of its relaxed
lexicographic bound certifies this concrete start; it does not certify every
possible in-progress timing state. Runs are sequential and retain no CPU graph.
"""
import argparse
from dataclasses import asdict
import hashlib
from pathlib import Path
import resource
import subprocess
import time

import moves
import rom_moves
import rom_proof
import rom_tables
from sae_rules import SaeGraph, SaeRules, SKILLS
from sae_timing import TimedAction, identity as timing_identity


def identity():
    sources = timing_identity()
    sources.update(rom_moves.identity())
    for name in ('verify_sae_timing.py', 'rom_proof.py', 'rom_tables.py'):
        path = Path(__file__).with_name(name)
        sources[str(path.relative_to(path.parents[2]))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return sources


def read_trace(path):
    lines = path.read_text().splitlines()
    if not lines:
        raise ValueError('Empty input schedule')
    head = lines[0].split()
    if len(head) != 6 or head[0] != 'HYPCADE_ROUTE_V2':
        raise ValueError('Expected an exact HYPCADE_ROUTE_V2 schedule')
    root, final = head[1:3]
    count, score, commands = map(int, head[3:])
    if count <= 0 or count != len(lines) - 1 or not 0 <= commands <= count or score < 0:
        raise ValueError('Invalid input schedule totals')
    steps, previous = [], root
    for line in lines[1:]:
        fields = line.split()
        if len(fields) != 7:
            raise ValueError('Incomplete input schedule row')
        control, press, release, until = map(int, fields[:4])
        source, target = fields[4:6]
        if source != previous or fields[6] not in ('0', '1'):
            raise ValueError('Broken input schedule chain')
        if any(len(h) != 32 or any(c not in '0123456789abcdef' for c in h) for h in (source, target)):
            raise ValueError('Invalid machine fingerprint')
        steps.append((TimedAction(control, press, release, until), source, target))
        previous = target
    if previous != final:
        raise ValueError('Input schedule does not end at its declared fingerprint')
    return dict(root=root, final=final, score=score, commands=commands, steps=steps)


def scalar_event(event):
    return {key: value for key, value in vars(event).items() if key != 'ram'}


def replay(rules, rom_path, trace_path, build_dir, start_delay=0, allowed_deaths=0):
    trace = read_trace(trace_path)
    started = time.monotonic()
    with rules.timed(rom_path, build_dir=build_dir, start_delay=start_delay) as run:
        initial = run.state()
        if initial.decision_hash != trace['root']:
            raise ValueError('Input schedule starts at a different machine/configuration')
        commands, events, boundaries, schedules = 0, [], [], []
        def event_row(event):
            row = scalar_event(event)
            if event.kind == 'ready':
                row['point'] = asdict(run.projection.project(event.ram))
            return row
        for i, (action, source, target) in enumerate(trace['steps']):
            before = run.state()
            if before.decision_hash != source:
                raise ValueError('Schedule source mismatch at input %d' % i)
            result = run.step(action)
            allowed = {result.state.decision_hash}
            if i == len(trace['steps']) - 1:
                allowed.add(result.state.victory_hash)
            if target not in allowed:
                raise ValueError('Schedule target mismatch at input %d' % i)
            if (result.executed_action.press_cycle, result.executed_action.release_cycle) != (action.press_cycle, action.release_cycle):
                raise ValueError('Instruction-aligned input times differ from the recorded schedule')
            if result.state.lives >= 0 and result.state.lives < initial.lives - allowed_deaths:
                raise ValueError('Winning schedule lost a life')
            commands += result.reward.commands
            events.extend(event_row(e) for e in result.events)
            boundaries.extend(asdict(b) for b in result.boundaries)
            schedules.append(dict(action=asdict(result.executed_action), source=source, target=target,
                                  reward=asdict(result.reward), point=asdict(run._point), score=result.state.score,
                                  accepted_commands=commands, pending=run._pending is not None or run._selected is not None))
        result = run.finish()
        commands += result.reward.commands
        events.extend(event_row(e) for e in result.events)
        boundaries.extend(asdict(b) for b in result.boundaries)
        success = next((e for e in events if e['kind'] == 'success'), None)
        if success is None:
            raise ValueError('No actual successful ROM end-handler observation')
        # The successful end handler blanks the life display. Check its entry
        # observation and every preceding boundary, rather than treating that
        # intentional blank as a lost life.
        before_end = [e for e in events if e['cycle'] <= success['cycle']]
        alive = (success['lives'] == initial.lives - allowed_deaths and
                 sum(e['kind'] == 'restart' for e in before_end) == allowed_deaths and
                 sum(e['kind'] == 'ready' and rules.record(e['scene'], e['step']).death
                     for e in before_end) == allowed_deaths and
                 not any(e['lives'] >= 0 and e['lives'] < initial.lives - allowed_deaths for e in before_end))
        if (commands, result.state.score, alive) != (trace['commands'], trace['score'], True):
            raise ValueError('Actual successful ROM end %r differs from schedule totals %r' %
                             ((commands, result.state.score, result.state.lives),
                              (trace['commands'], trace['score'], initial.lives)))
        return dict(trace_sha256=hashlib.sha256(trace_path.read_bytes()).hexdigest(),
                    initial=initial.decision_hash, final=result.state.victory_hash,
                    skill=rules.skill, difficulty=rules.difficulty, start_delay=start_delay,
                    commands=commands, score=result.state.score, lives=success['lives'],
                    end_display_lives=result.state.lives,
                    events=events, boundaries=boundaries, schedules=schedules,
                    native_memory_bytes=run.timing.memory_bytes,
                    seconds=time.monotonic() - started, verified=True)


def certify(rules, result):
    """Bounds + a matching feasible schedule, never a sampled coverage proof."""
    started = time.monotonic()
    model = SaeGraph(rules)
    graph = rom_proof.closure(model, model.coverage_seeds())
    values = rom_proof.solve(graph)
    root = graph['states'].index(model.start())
    bounds = {key: value[root] for key, value in values.items()}
    return dict(bounds=bounds, states=len(graph['states']),
                commands_optimal=result['commands'] == bounds['fewest'],
                score_optimal=result['score'] == bounds['highest_score'],
                shortest_lexicographic_optimal=(result['commands'], result['score']) ==
                    (bounds['fewest'], bounds['score_at_fewest']),
                score_lexicographic_optimal=(result['score'], result['commands']) ==
                    (bounds['highest_score'], bounds['fewest_at_score']),
                scope='This concrete initial machine; surviving accepted-command objective',
                seconds=time.monotonic() - started)


def timing_frontiers(graph, values, objective):
    """Locate only the last controllable edges before value-sensitive reads.

    This is a bounded witness-search heuristic. An equal relaxed bound plus
    exact replay is the certificate; the finite delay probes alone prove
    nothing about unsampled timing states. All original graph edges remain.
    """
    def value(v):
        if values['fewest'][v] is None:
            return None
        if objective == 'shortest':
            return values['fewest'][v], -values['score_at_fewest'][v]
        return -values['highest_score'][v], values['fewest_at_score'][v]

    incoming = [[] for _ in graph['states']]
    sensitive = []
    for u, actions in enumerate(graph['actions']):
        for label, targets in actions:
            if value(u) is None:
                continue
            for v in targets:
                if value(v) is not None:
                    incoming[v].append((u, label))
            if len({value(v) for v in targets}) > 1:
                sensitive.append((u, label))
    pending, visited, frontier = [], set(), set()
    for u, label in sensitive:
        if label[0] > 0:
            frontier.add((u, label[0]))
        else:
            pending.append(u)
    for v in pending:
        if v in visited:
            continue
        visited.add(v)
        for u, label in incoming[v]:
            if label[0] > 0:
                frontier.add((u, label[0]))
            elif label[0] == 0:
                pending.append(u)
    probes = sorted({(graph['states'][u].scene, graph['states'][u].step, c) for u, c in frontier})
    return dict(unequal_branch_actions=len(sensitive), last_input_records=probes)


def write_policy(graph, values, objective, path):
    rows, _ = rom_proof.ranked(graph, values, objective)
    grouped = {}
    for state, ranked in zip(graph['states'], rows):
        if not ranked:
            continue
        labels = tuple(row[1] for row in ranked)
        key = state.scene, state.step, state.score_suppressed
        if key in grouped and grouped[key] != labels:
            raise ValueError('Scene-only witness policy would discard relevant ROM context')
        grouped[key] = labels
    path.write_text('HYPCADE_ROM_POLICY_V3\n' + ''.join(
        '%d %d %d %d %d %d 3 0 0 %d\n' % (scene, step, control, window, outcome, rank, suppressed)
        for (scene, step, suppressed), labels in sorted(grouped.items())
        for rank, (control, window, outcome) in enumerate(labels)))


def matrix(args, rom, sources):
    """One full play per setting; probe only a proven unequal branch frontier."""
    build_dir = (args.output / 'build').resolve()
    player = rom_moves.build(build_dir)
    report = dict(schema=1, sources=sources, rom_sha256=hashlib.sha256(rom).hexdigest(),
                  start_delay=args.start_delay, results=[],
                  scope='Exact initial-start lexicographic optima; no intentional deaths; no arbitrary-state timing proof')
    started = time.monotonic()
    for skill in SKILLS:
        for difficulty in (0, 1):
            rules = SaeRules(rom, skill, difficulty)
            model = SaeGraph(rules)
            graph = rom_proof.closure(model, model.coverage_seeds())
            values = rom_proof.solve(graph)
            root = graph['states'].index(model.start())
            for objective in ('shortest', 'highest-score'):
                tag = '%s-d%d-%s' % (skill, difficulty, objective)
                policy = (args.output / (tag + '.policy')).resolve()
                write_policy(graph, values, objective, policy)
                phase = timing_frontiers(graph, values, objective)
                wanted = ((values['fewest'][root], values['score_at_fewest'][root])
                          if objective == 'shortest' else
                          (values['fewest_at_score'][root], values['highest_score'][root]))
                attempts = []
                result = None
                # 0: normal ROM-ranked play. Only if the bound is missed, vary
                # timing at the last input frontier before a value-sensitive R
                # read. No global timing enumeration or invented probabilities.
                for delay in (0, 4096, 8192, 16384):
                    if delay and not phase['last_input_records']:
                        break
                    attempt = '%s-t%d' % (tag, delay)
                    trace = (args.output / (attempt + '.trace')).resolve()
                    command = [str(player), str(args.rom.resolve()), 'sae', skill,
                               str(args.start_delay), str(policy), str(trace), '3600', str(difficulty)]
                    if delay:
                        probe = (args.output / (attempt + '.timing')).resolve()
                        probe.write_text('HYPCADE_ROM_TIMING_V1\n' + ''.join(
                            '%d %d %d %d\n' % (*row, delay) for row in phase['last_input_records']))
                        command.append(str(probe))
                    log = args.output / (attempt + '.stdout')
                    with log.open('w') as out, (args.output / (attempt + '.stderr')).open('w') as err:
                        played = subprocess.run(command, stdout=out, stderr=err, timeout=120)
                    summary = next((r for r in rom_moves.records(log) if r['type'] == 'rom_play'), {})
                    attempts.append(dict(delay=delay, returncode=played.returncode, play=summary))
                    if played.returncode == 0 and (summary.get('moves'), summary.get('score')) == wanted:
                        result = replay(rules, args.rom, trace, build_dir, args.start_delay)
                        result['certificate'] = certify(rules, result)
                        if not result['certificate'][('shortest' if objective == 'shortest' else 'score') + '_lexicographic_optimal']:
                            raise ValueError('Fresh independent certificate disagrees with witness construction')
                        if args.negative_controls:
                            result['negative_controls'] = negative_controls(rules, args.rom, trace, build_dir,
                                                                            result, args.start_delay)
                        moves.atomic_json(args.output / (tag + '-replay.json'), result)
                        break
                row = dict(skill=skill, difficulty=difficulty, objective=objective, target=wanted,
                           timing_analysis=phase, attempts=attempts, optimal=result is not None)
                if result is not None:
                    row.update({k: v for k, v in result.items() if k not in ('events', 'boundaries', 'schedules')})
                report['results'].append(row)
                report.update(elapsed_seconds=time.monotonic() - started,
                              peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                              peak_child_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
                              all_optimal=all(r['optimal'] for r in report['results']))
                moves.atomic_json(args.output / 'report.json', report)
                print('%s: %s, target=%r, timing trials=%d' %
                      (tag, 'OPTIMAL' if result is not None else 'UNRESOLVED', wanted, len(attempts)), flush=True)
    if identity() != sources:
        raise ValueError('Sources changed during strategy validation')
    if not report['all_optimal']:
        raise SystemExit(1)


def negative_controls(rules, rom_path, trace_path, build_dir, replayed, start_delay=0):
    """Withhold an actual command and check automatic death/restart binding.

    Use the last accepted input before an R-sensitive boundary in the supplied
    trace. This is derived from observed ROM events, not a hand-coded move index.
    """
    trace = read_trace(trace_path)
    accepted, found = None, None
    for event in replayed['events']:
        if event['kind'] == 'accepted':
            accepted = event
        elif event['kind'] == 'refresh' and accepted is not None:
            record = rules.record(accepted['scene'], accepted['step'])
            if record.default < 128 and rules.record(record.scene, record.default).death:
                found = next((i for i, (action, _, _) in enumerate(trace['steps'])
                              if action.control and action.press_cycle <= accepted['cycle'] <= action.release_cycle), None)
                if found is not None:
                    break
    if found is None:
        raise ValueError('No fatal omitted-input control precedes a selector read in this trace')
    with rules.timed(rom_path, build_dir=build_dir, start_delay=start_delay) as run:
        for action, _, _ in trace['steps'][:found]:
            run.step(action)
        run.save()
        before = run.state()
        try:
            run.step(TimedAction(16, before.cycle - 1, before.cycle, before.cycle))
        except ValueError:
            pass
        else:
            raise ValueError('Past input schedule was accepted')
        if run.state() != before:
            raise ValueError('Invalid input schedule mutated the machine')
        result = run.wait(before.cycle + 40_000_000)
        if result.reward.commands or result.state.lives != before.lives - 1:
            raise ValueError('Withheld-input control did not lose exactly one life without an accepted command')
        if not any(b.recovery for b in result.boundaries):
            raise ValueError('Withheld-input control did not exercise ROM life restart')
        run.restore()
        repeated = run.wait(before.cycle + 40_000_000)
        if repeated != result:
            raise ValueError('Checkpoint restore changed timed execution')
        return dict(withheld_step=found, commands=0, lives_before=before.lives,
                    lives_after=result.state.lives, deterministic_restore=True,
                    invalid_schedule_preserves_state=True,
                    boundaries=[asdict(b) for b in result.boundaries])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--trace', type=Path, action='append')
    mode.add_argument('--matrix', action='store_true', help='Generate and certify both objectives at all SAE settings')
    parser.add_argument('--skill', choices=SKILLS, default='cadet')
    parser.add_argument('--difficulty', type=int, choices=(0, 1), default=0)
    parser.add_argument('--start-delay', type=float, default=0)
    parser.add_argument('--negative-controls', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    sources = identity()
    rom = rom_tables.load(args.rom, 'sae')
    if args.matrix:
        matrix(args, rom, sources)
        return
    rules = SaeRules(rom, args.skill, args.difficulty)
    report = dict(schema=1, sources=sources, rom_sha256=hashlib.sha256(rom).hexdigest(), results=[])
    first_replay = None
    for i, trace in enumerate(args.trace):
        result = replay(rules, args.rom, trace, args.output / 'build', args.start_delay)
        result['certificate'] = certify(rules, result)
        if first_replay is None:
            first_replay = result
        moves.atomic_json(args.output / ('replay-%d.json' % i), result)
        report['results'].append({k: v for k, v in result.items() if k not in ('events', 'boundaries', 'schedules')})
        print('%s: score=%d commands=%d; score optimum=%s, command optimum=%s' %
              (trace.name, result['score'], result['commands'], result['certificate']['score_optimal'],
               result['certificate']['commands_optimal']), flush=True)
    if args.negative_controls:
        report['negative_controls'] = negative_controls(rules, args.rom, args.trace[0], args.output / 'build', first_replay, args.start_delay)
    if identity() != sources:
        raise ValueError('Sources changed during timing validation')
    report['peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report['peak_child_rss_kib'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    report['all_verified'] = all(r['verified'] for r in report['results'])
    moves.atomic_json(args.output / 'report.json', report)


if __name__ == '__main__':
    main()
