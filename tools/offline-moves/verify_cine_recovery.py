#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Audit reachable Ace transitions and life restarts against original ROM code."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

import cine_recovery_model
import rom_kernel
import rom_proof
import rom_tables


def ram_for(model, state, outcome):
    ep, scene, step, cursor, replayed, checkpoint, alias = state
    ram = bytearray(1024)
    ram[0x11] = 8 | (128 if model.game == 'sae' and model.checkpoints else 0)
    ram[0xd4] = model.base.skill_number
    ram[0x35], ram[0x36], ram[0x37] = replayed * 8, ep | 128, checkpoint
    ram[0x60 + ep] = 1
    for i, q in enumerate(model.queue(alias)):
        ram[0x80 + i] = q | 128
    ram[0xd0:0xd2] = (0xa080 + cursor).to_bytes(2, 'little')
    rec = model.record_for(state)
    ram[0x200], ram[0x201], ram[0x202] = rec['trailer'][0], rec['trailer'][1], scene | 128
    ram[0x205] = rec['trailer'][4]
    extension = iter(rec['extension'])
    for flag, at in ((32, 0x207), (64, 0x209)):
        if rec['trailer'][4] & flag:
            ram[at], ram[at + 1] = next(extension), next(extension)
    ram[14], ram[15], ram[0x12] = scene | 128, step, outcome
    return ram


def audit(model, kernel, graph):
    cases = 0
    for state, actions in zip(graph['states'], graph['actions']):
        recovery = model.record_for(state)['death']
        alternatives = [(None, model.recover(state))] if recovery else [
            (outcome, model.targets(state, outcome)) for outcome in sorted({label[2] for label, ts in actions if ts})]
        for outcome, expected in alternatives:
            high = (state[5] if recovery else outcome) & 128
            observed = set()
            for phase in range(2 if high else 1):
                ram = ram_for(model, state, 0 if recovery else outcome)
                if recovery:
                    ram[0x35] |= 128
                    ram[0x12], ram[15] = state[1] | 128, 0
                    ram, _ = kernel.call(ram, 0x1465, stop=0x1492, refresh=phase)
                else:
                    ram, _ = kernel.call(ram, 0x1c8c, refresh=phase)
                    ram, _ = kernel.call(ram, 0x14c9, stop=0x1492, refresh=phase)
                # Actual loader's checkpoint tail. Earlier parsing copies the
                # flags and leaves HL immediately before the checkpoint byte.
                target = (ram[0x36] & 127, ram[14] & 127, ram[15],
                          int.from_bytes(ram[0xd0:0xd2], 'little') - 0xa080,
                          (ram[0x35] >> 3) & 1)
                rec = model.base.record_for(target)
                ram[0x205] = rec['trailer'][4]
                ram, _ = kernel.call(ram, 0x16b9, stop=0x16d4, hl=rec['end'] - 2)
                alias = int(ram[0x82] & 127 == 30) if model.game == 'sae' and model.skill == 'ace' else 0
                actual = (*target, ram[0x37], alias)
                if actual not in expected:
                    raise ValueError('Original-ROM mismatch %s %s d%d %r outcome=%r -> %r expected=%r' %
                                     (model.game, model.skill, model.difficulty, state, outcome, actual, expected))
                observed.add(actual)
                cases += 1
            if observed != set(expected):
                raise ValueError('Unexercised branch at %r: %r' % (state, set(expected) - observed))
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--roms', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    rows = []
    for game in ('ace', 'sae'):
        rom = rom_tables.load(args.roms / (game + '.zip'), game)
        kernel = rom_kernel.Kernel(rom, args.output / 'build')
        for skill in ('cadet', 'captain', 'ace'):
            for difficulty in range(1 if game == 'ace' else 2):
                model = cine_recovery_model.Model(rom, game, skill, difficulty)
                graph = rom_proof.closure(model, model.coverage_seeds())
                result = rom_proof.solve(graph)
                cases = audit(model, kernel, graph)
                automatic_loops = [(state, label) for state, actions in zip(graph['states'], graph['actions'])
                                   for label, targets in actions if not label[0] and
                                   graph['states'].index(state) in targets]
                if automatic_loops:
                    raise ValueError('Reachable automatic loop: %r' % automatic_loops[:1])
                row = dict(game=game, skill=skill, difficulty=difficulty, states=len(graph['states']),
                           original_rom_cases=cases, automatic_loops=0,
                           recovery_sources=len(model.recoveries), alias_states=sum(s[-1] for s in graph['states']),
                           minimum_commands=result['fewest'][0], optimistic_maximum_score=result['highest_score'][0],
                           rom_sha256=hashlib.sha256(rom).hexdigest())
                rows.append(row)
                print(json.dumps(row), flush=True)
    sources = {n: hashlib.sha256((Path(__file__).parent / n).read_bytes()).hexdigest() for n in
               ('verify_cine_recovery.py', 'cine_recovery_model.py', 'cine_global_model.py',
                'rom_tables.py', 'rom_proof.py', 'rom_kernel.py', 'rom_kernel.c')}
    report = dict(all_passed=True, cases=rows, sources=sources,
                  seconds=time.monotonic() - started, peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  scope='Finite abstract-domain original-ROM transition audit; no timing/play/replay or Android claim. SAE history choices overapproximated outside aliased queue bytes.')
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
