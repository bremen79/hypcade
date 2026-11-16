#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Finite ROM selector kernels and compositional DL1 scheduler invariants.

No enumeration of complete room permutations or CPU snapshots. Refresh phases
are retained as explicit inputs, never silently given uniform probabilities.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import resource
import time

import cine_room_optimality
import rom_kernel
import rom_proof
import rom_tables


def descriptors(rom, game):
    if game == 'dle21':
        base, count = 0x2203, 23
    else:
        at = rom.find(bytes.fromhex('3a54a0cb27cb27'))
        if at < 3 or rom[at - 3] != 0x21:
            raise ValueError('Unknown descriptor reference')
        base, count = rom_tables.word(rom, at - 2), 13
    result = {}
    for ep in range(1, count + 1):
        at = base + 4 * ep
        pointer = rom_tables.word(rom, at)
        flags, mask = rom[at + 2:at + 4]
        n = (mask.bit_length() if flags & 7 else 1)
        result[ep] = dict(flags=flags, mask=mask, scenes=[v & 127 for v in rom[pointer:pointer + n]])
    return result


def room_effects(model, graph, playable_scenes):
    effects = [set() for _ in graph['states']]
    terminals = list(model.return_labels)
    for u in rom_proof.decision_dag(graph)['order']:
        state = graph['states'][u]
        if model.won(state):
            effects[u] = {terminals[state[1]] if state[0] == 128 else ('win',)}
        else:
            for label, targets in graph['actions'][u]:
                for v in targets:
                    effects[u].update(effects[v])
    # Every off-policy state with a surviving exit must have the same exit
    # effect, except the authored DLE hub. This proves suffix additivity at
    # the semantic room boundary, not just along selected winning routes.
    mixed = []
    for state, exits in zip(graph['states'], effects):
        if state[0] not in playable_scenes:
            continue
        if len(exits) > 1:
            if model.game != 'dle21' or state[0] not in (20, 21, 71, 72):
                raise ValueError('Unexpected action-dependent scheduler effect: %r' % (state,))
            if exits != {('explicit', 12), ('explicit', 16), ('explicit', 20)}:
                raise ValueError('Unknown DLE hub destinations')
            mixed.append(state)
    return effects, mixed


def selector_kernel(rom, game, kernel):
    # The selector's shared mask dispatcher has this unique signature.
    entry = rom.find(bytes.fromhex('7ee607fe0028'))
    if entry < 0:
        raise ValueError('Unknown regular selector')
    table = []
    cases = 0
    extra_pointer = 0x38af
    has_extra = game in ('lair_a', 'lair_b', 'lair_c', 'lair_d')
    for enabled in (False, True):
        for used in range(32 if has_extra else 1):
            for mask in range(7):
                phases = []
                # Audit all 128 refresh residues, checking that the exact
                # transition depends only on the low THREE bits. Repeated
                # reads of R within the routine stay correlated.
                for seed in range(128):
                    ram = bytearray(1024)
                    ram[0x10] = (4 if enabled else 0) | (0 if has_extra else 2)
                    ram[0x11] = 8
                    ram[0x200] = mask
                    for i in range(5):
                        ram[0x70 + i] = 128 if used & (1 << i) else 0
                    out, regs = kernel.call(ram, entry, hl=0xa200, bc=0x1000, refresh=seed)
                    ptr = regs['bc']
                    choice = ptr - extra_pointer + 3 if has_extra and extra_pointer <= ptr < extra_pointer + 5 else ptr - 0x1000
                    if not 0 <= choice < (8 if has_extra else 3):
                        raise ValueError('Selector pointer outside decoded alternatives')
                    next_used = sum(bool(out[0x70 + i]) << i for i in range(5))
                    result = (choice, out[0x200] & 7, next_used, regs['refresh'] & 7)
                    if choice < 3:
                        assert not mask & (1 << choice) and result[1] == mask | (1 << choice)
                        assert next_used == used
                    else:
                        assert not used & (1 << (choice - 3)) and next_used == used | (1 << (choice - 3))
                        assert result[1] == mask
                    if seed < 8:
                        phases.append(result)
                    elif result != phases[seed & 7]:
                        raise ValueError('Selector requires more than three phase bits')
                    cases += 1
                table.append(dict(enabled=enabled, used=used, mask=mask, phases=phases))
    return dict(cases=cases, phase_bits=3, transitions=table,
                probability_assumption=None,
                interpretation='Exact conditional selector transducer; phase distribution and inter-room phase evolution are not assumed')


def progress_audit(kernel, game, rom):
    entry = rom.find(bytes.fromhex('3a12a0cb7fc821050019cb66c02107001934'))
    if entry < 0:
        raise ValueError('Unknown progress routine')
    cases = 0
    for threshold in (5, 9):
        for count in range(256):
            for hard in (0, 16):
                for high in (0, 128):
                    ram = bytearray(1024)
                    ram[0x11] = 16 if threshold == 9 else 0
                    ram[0x35], ram[0x37], ram[0x12] = hard, count, high
                    out, _ = kernel.call(ram, entry)
                    after = count if hard or not high else (count + 1) & 255
                    expected_flag = hard | (16 if high and after == threshold else 0)
                    if out[0x37] != after or out[0x35] != expected_flag:
                        raise ValueError('Progress counter model differs from ROM: %s %s %s %s -> %s %s wanted %s %s' % (game, threshold, count, hard, out[0x37], out[0x35], after, expected_flag))
                    cases += 1
    return dict(cases=cases, thresholds=[5, 9], normal_first_lap_groups=[0, 0, 4, 8],
                invariant='Harder-version flag is monotone during surviving play; start counter is 1, so thresholds affect selection after 4/8 completions')


def reward_audit(kernel, game, rom):
    """Fixed per-record score and carries, independent of the SAE gate bit."""
    load = rom.find(bytes.fromhex('3e0ffda60021'))
    transfer = rom.find(bytes.fromhex('3a13a0fe00c8'))
    if load < 0 or transfer < 0 or rom_tables.word(rom, load + 6) != rom_tables.LAYOUTS[game]['score']:
        raise ValueError('Unrecognized DL1 score routines')
    store = rom.find(bytes.fromhex('2213a0'), load, load + 32)
    if store < 0:
        raise ValueError('Missing score-load destination')
    cases = 0
    for rank in range(16):
        award = rom_tables.word(rom, rom_tables.LAYOUTS[game]['score'] + 2 * rank)
        ram = bytearray(1024)
        ram[0x200] = rank
        actual, _ = kernel.call(ram, load, stop=store + 3)
        if int.from_bytes(actual[0x13:0x15], 'little') != award:
            raise ValueError('DL1 fixed score load mismatch')
        cases += 1
        for gate in (0, 2):
            for baseline in (0, 0x12fffe):
                ram = bytearray(1024)
                ram[0xA] = gate
                ram[0x13:0x15] = award.to_bytes(2, 'little')
                ram[0x32:0x35] = baseline.to_bytes(3, 'little')
                actual, _ = kernel.call(ram, transfer, stop=transfer + 24 if award & 255 else 0xdead)
                expected = baseline + award if award & 255 else baseline
                if int.from_bytes(actual[0x32:0x35], 'little') != expected:
                    raise ValueError('DL1 fixed score transfer mismatch')
                cases += 1
    return dict(cases=cases, load_pc=load, transfer_pc=transfer,
                invariant='Fixed per-record award, no timing multiplier and no SAE A00A.1 suppression')


def dle_reduction(rom, desc, model, graph, values):
    idx = {s: u for u, s in enumerate(graph['states'])}
    def value(scene):
        u = idx[(scene, 0)]
        return values['fewest'][u], values['highest_score'][u]
    # Loader 09CB independently picks adjacent mirror IDs at the start of
    # these scenes. Verify equal root values; retain actual IDs after detours.
    mirrors = []
    for raw in rom[0x22f4:rom.index(255, 0x22f4)]:
        scene = raw & 127
        if value(scene) != value(scene + 1):
            raise ValueError('DLE mirror changes the objective')
        mirrors.append([scene, scene + 1])
    for ep, scenes, flags, mask in ((1, [50, 38], 9, 3),
                                  (5, [40, 39, 39], 10, 7),
                                  (9, [42, 41, 41], 10, 7)):
        if desc[ep] != dict(flags=flags, mask=mask, scenes=scenes):
            raise ValueError('DLE chapter loop descriptor changed')
    chapters = []
    for start in (12, 16, 20):
        chapter = []
        for ep in range(start, start + 3):
            if desc[ep]['flags'] != 10 or desc[ep]['mask'] != 7:
                raise ValueError('DLE final chapter is not fixed-order exhaustion')
            chapter.extend(desc[ep]['scenes'])
        chapters.append(chapter)
    if any(collections.Counter(c) != collections.Counter(chapters[0]) for c in chapters):
        raise ValueError('DLE hub choices change the remaining room multiset')
    zero = [38, 39, 40, 41, 42, 44, 45, 46, 47, 48, 49]
    if any(value(s) != (0, 0) for s in zero):
        raise ValueError('Chapter intermission has a nonconstant objective cost')
    return dict(mirror_pairs=mirrors, final_chapter_multisets=chapters,
                zero_cost_intermissions=zero,
                simplification='Discard intermission decisions, sum exhausted room multisets, quotient objective-equivalent mirrors; hub choice has a constant suffix')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--roms', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    started = time.monotonic()
    for game in cine_room_optimality.GAMES:
        rom = rom_tables.load(args.roms / (game + '.zip'), game)
        kernel = rom_kernel.Kernel(rom, args.output / 'build')
        model = cine_room_optimality.Model(rom, game)
        graph = model.graph()
        values = rom_proof.solve(graph)
        desc = descriptors(rom, game)
        playable = {0} | {s for d in desc.values() for s in d['scenes']}
        if game == 'dle21':
            for raw in rom[0x22f4:rom.index(255, 0x22f4)]:
                playable.update((raw & 127, (raw & 127) + 1))
        else:
            offset = 40 if game in ('lair_a', 'lair_b', 'lair_c', 'lair_d') else 42
            playable.update(s + offset for s in list(playable) if s + offset < model.spec['count'])
            if offset == 40:
                playable.update(range(80, 85))
        effects, mixed = room_effects(model, graph, playable)
        row = dict(game=game, rom_sha256=hashlib.sha256(rom).hexdigest(), descriptors=desc,
                   room_states=len(graph['states']), hub_states=len(mixed),
                   playable_scenes=sorted(playable), per_record_single_exit_checked=True)
        row['rewards'] = reward_audit(kernel, game, rom)
        if game == 'dle21':
            row['reduction'] = dle_reduction(rom, desc, model, graph, values)
        else:
            if any(desc[ep]['flags'] != (10 if ep == 13 else 2) or desc[ep]['mask'] != 7 for ep in desc):
                raise ValueError('US three-lap scheduler changed')
            row['selector'] = selector_kernel(rom, game, kernel)
            row['progress'] = progress_audit(kernel, game, rom)
            row['three_lap_gate'] = desc[13]['scenes']
        rows.append(row)
        print(game, 'room effects and scheduler invariants checked',
              'native selector cases', row.get('selector', {}).get('cases', 0), flush=True)
    sources = {n: hashlib.sha256((Path(__file__).parent / n).read_bytes()).hexdigest() for n in
               ('verify_dl1_scheduler.py', 'cine_room_optimality.py', 'rom_tables.py',
                'rom_proof.py', 'rom_kernel.py', 'rom_kernel.c')}
    report = dict(cases=rows, sources=sources, all_passed=True,
                  seconds=time.monotonic() - started, peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  limits='Semantic room-boundary additivity and finite selector/progress audits. Does not prove refresh-phase independence from input timing or a stochastic probability law.')
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
