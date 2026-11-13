#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Export all decoded ROM move rules, independently of sampled winning games."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import moves as move_tools
import rom_tables

ROOT = Path(__file__).resolve().parent
OBJECTIVES = ('shortest', 'highest-score')
FORMAT = 'hypcade-rom-rules'
COVERAGE = dict(all_decoded_windows_exported=True, sampled_routes_required=False,
                reachable_contexts_proven=False, execution_timing_proven=False,
                global_optimum_proven=False)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_identity():
    return {name: digest(ROOT / name) for name in
            ('export_rom_moves.py', 'rom_tables.py', 'moves.py')}


def compile_rules(data, policies):
    """Keep every decoded window, even when the local planner cannot rank it.

    A ROM slot is not a runtime slot: the original loader can skip conditional
    records. Preserve the identity and condition fields; never substitute a
    branch value or accepted frame observed in one play.
    """
    records = {r['address']: r for r in data['records']}
    nodes = {(n['scene'], n['step']): n for n in data['nodes']}
    ranks = {goal: {(tuple(c['source']), c['control'], c['window'], c['outcome']): c
                    for c in policy['choices']} for goal, policy in policies.items()}
    rules = []
    for key, node in sorted(nodes.items()):
        record = records[node['address']]
        source_dispatch = record['death'] or record['scene_exit'] or record['system']
        # Include terminal/system input records too, but do not call them playable.
        choices = [(None, None, record['trailer'][1])]
        choices += [(entry, window, window['outcome']) for entry in record['inputs']
                    for window in entry['windows']]
        for entry, window, outcome in choices:
            slot = entry['slot'] if entry else None
            local_window = window['window'] if window else None
            control = entry['control'] if entry else 0
            policy_window = slot * 3 + local_window if entry else 0
            target = None if outcome == 255 or source_dispatch else ((outcome & 127, 0) if outcome & 128
                                                  else (key[0], outcome))
            dest = records[nodes[target]['address']] if target in nodes else None
            if source_dispatch:
                classification = 'source-dispatch'
            elif window is not None and not window['ticks']:
                classification = 'empty-window'
            elif control is None:
                classification = 'unsupported-control'
            elif outcome == 255:
                classification = 'ignored'
            elif dest is None:
                classification = 'unresolved-target'
            elif dest['death']:
                classification = 'death'
            else:
                classification = 'candidate'
            ranked = {}
            for goal, choices_by_key in ranks.items():
                choice = choices_by_key.get((key, control, policy_window, outcome))
                if choice is not None and classification == 'candidate':
                    ranked[goal] = {name: choice[name] for name in
                                    ('rank', 'remaining_moves', 'remaining_score')}
            rules.append(dict(
                id='%d:%d:%s' % (*key, 'wait' if entry is None else '%d:%d' % (slot, local_window)),
                source=list(key), record_address=node['address'], rom_slot=slot,
                window=local_window, control=control, outcome=outcome,
                target=list(target) if target is not None else None,
                dispatch=bool(target is not None and outcome & 128),
                classification=classification, objectives=ranked,
                # These are decoding facts, not a complete execution predicate.
                loader=None if entry is None else dict(
                    rom_control=entry['rom_control'], header=entry['header'],
                    extra=entry['extra'], selector=entry['selector'],
                    condition_interpretation='original-rom-loader'),
                timing=None if entry is None else dict(
                    delay_ticks=entry['delay_ticks'], ticks=window['ticks'],
                    preceding_ticks=[w['ticks'] for w in entry['windows'][:local_window]],
                    basis='rom-before-runtime-adjustment', accepted_frame=None),
                source_award=record['award'],
                target_award=dest['award'] if dest is not None else None,
                causal_score_gain_proven=False))
    return rules


def statistics(data, rules, policies):
    return dict(scene_slots=len(data['groups']), nodes=len(data['nodes']),
                unique_records=len(data['records']), graph_edges=len(data['edges']),
                rules=len(rules), input_windows=sum(r['control'] != 0 for r in rules),
                classifications=dict(sorted(Counter(r['classification'] for r in rules).items())),
                ranked={goal: sum(goal in r['objectives'] for r in rules) for goal in OBJECTIVES},
                unranked_candidates=sum(r['classification'] == 'candidate' and not r['objectives'] for r in rules),
                cyclic_nodes={goal: policies[goal]['cyclic_nodes'] for goal in OBJECTIVES},
                unresolved_targets=len(data['unresolved_targets']))


def export(rom_path, game, output):
    """Publish a reproducible package in a new directory; never touch the APK."""
    output = Path(output)
    if output.exists():
        raise ValueError('Output already exists; choose a new directory')
    chips = move_tools.identity(rom_path, game)
    sources = source_identity()
    data = rom_tables.inventory(rom_tables.load(rom_path, game), game)
    if data['unresolved_targets']:
        raise ValueError('Unresolved graph targets; refusing an incomplete structural export')
    policies = {goal: rom_tables.policies(data, goal) for goal in OBJECTIVES}
    rules = compile_rules(data, policies)
    stats = statistics(data, rules, policies)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='rom-export-staging-', dir=output.parent))
    try:
        move_tools.atomic_json(staging / 'inventory.json', data)
        move_tools.atomic_json(staging / 'rules.json', rules)
        for goal, policy in policies.items():
            move_tools.atomic_json(staging / (goal + '-policy.json'), policy)
            rom_tables.write_policy(staging / (goal + '.policy'), policy)
        manifest = dict(
            format=FORMAT, schema=1, game=game, rom_chips=chips, sources=sources,
            files={p.name: digest(p) for p in sorted(staging.iterdir())}, statistics=stats,
            coverage=COVERAGE,
            limits=[
                'Pointer-table boundaries are inferred; structural closure is not proof of every reachable scene.',
                'ROM loader conditions and skill-dependent timer adjustment remain authoritative at runtime.',
                'Local scene-exit rankings do not prove global optimality; cycles and system dispatch remain unresolved.',
                'A target award is not proof that a press caused points. Candidates require causal replay validation.',
                'bundle_rom_moves.py includes these complete policies in the APK; sampled plays supply timing calibration, not the coverage boundary.'])
        move_tools.atomic_json(staging / 'manifest.json', manifest)
        verify(staging, rom_path)
        if sources != source_identity():
            raise ValueError('Exporter sources changed during export')
        if output.exists():
            raise ValueError('Output appeared during export')
        staging.rename(output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return manifest


def verify(folder, rom_path=None):
    """Check hashes and reconstruct rules/ranks; optionally re-decode the ROM."""
    folder = Path(folder)
    manifest = json.loads((folder / 'manifest.json').read_text())
    if manifest['format'] != FORMAT or manifest['schema'] != 1:
        raise ValueError('Unsupported export format')
    if manifest['coverage'] != COVERAGE:
        raise ValueError('Unsupported coverage claims')
    expected = {'inventory.json', 'rules.json'} | {goal + suffix for goal in OBJECTIVES
                                                  for suffix in ('-policy.json', '.policy')}
    if set(manifest['files']) != expected:
        raise ValueError('Unexpected package file list')
    for name, sha256 in manifest['files'].items():
        path = folder / name
        if path.is_symlink() or digest(path) != sha256:
            raise ValueError('Package checksum mismatch: ' + name)
    data = json.loads((folder / 'inventory.json').read_text())
    if data['game'] != manifest['game'] or data['unresolved_targets']:
        raise ValueError('Invalid graph identity or unresolved targets')
    if rom_path is not None:
        if move_tools.identity(rom_path, manifest['game']) != manifest['rom_chips']:
            raise ValueError('ROM identity differs from package')
        if rom_tables.inventory(rom_tables.load(rom_path, manifest['game']), manifest['game']) != data:
            raise ValueError('Inventory differs from ROM')
    policies = {goal: rom_tables.policies(data, goal) for goal in OBJECTIVES}
    rules = compile_rules(data, policies)
    for goal, policy in policies.items():
        if json.loads((folder / (goal + '-policy.json')).read_text()) != policy:
            raise ValueError('Policy does not match graph: ' + goal)
        lines = ['HYPCADE_ROM_POLICY_V1'] + ['%d %d %d %d %d %d' %
                 (*c['source'], c['control'], c['window'], c['outcome'], c['rank']) for c in policy['choices']]
        if (folder / (goal + '.policy')).read_text() != '\n'.join(lines) + '\n':
            raise ValueError('Native policy differs from graph: ' + goal)
    if json.loads((folder / 'rules.json').read_text()) != rules:
        raise ValueError('Rules do not cover the decoded graph')
    if statistics(data, rules, policies) != manifest['statistics']:
        raise ValueError('Coverage statistics do not match graph')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    generate = sub.add_parser('export', help='Decode a supported ROM without simulating games')
    generate.add_argument('--game', choices=rom_tables.LAYOUTS, required=True)
    generate.add_argument('--rom', type=Path, required=True)
    generate.add_argument('--output', type=Path, required=True)
    check = sub.add_parser('verify', help='Check an export, optionally against its original ROM')
    check.add_argument('directory', type=Path)
    check.add_argument('--rom', type=Path)
    args = parser.parse_args()
    try:
        manifest = export(args.rom, args.game, args.output) if args.command == 'export' else verify(args.directory, args.rom)
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, 'Export failed: %s\n' % error)
    print(json.dumps(dict(game=manifest['game'], **manifest['statistics']), indent=2), flush=True)


if __name__ == '__main__':
    main()
