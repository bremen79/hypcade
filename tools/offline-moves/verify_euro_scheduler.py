#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Original-ROM queue/recovery invariants, without enumerating permutations."""
import argparse
import collections
import hashlib
import json
from pathlib import Path

import euro_optimality
import euro_tables
import rom_kernel
import rom_proof


def put(ram, offset, value):
    ram[offset:offset + 2] = value.to_bytes(2, 'little')


def word(ram, offset):
    return int.from_bytes(ram[offset:offset + 2], 'little')


def recoveries(kernel, game, roots):
    cases = 0
    for player in range(2):
        base = 0xa002 + player * 128
        head_at, end_at = 0x13a + 2 * player, 0x13e + 2 * player
        count = 36 if game == 'laireuro' else 17
        for head in range(count):
            for end in range(count):
                ram = bytearray(1024)
                queue = roots[:count]
                for i, root in enumerate(queue):
                    put(ram, base - 0xa000 + 2 * i, root)
                put(ram, head_at, base + 2 * head)
                put(ram, end_at, base + 2 * end)
                put(ram, 0x154, 0xa000 + head_at)
                put(ram, 0x156, 0xa000 + end_at)
                put(ram, 0x158, base + 2 * count)
                put(ram, 0x15c, base)
                ram[0x152] = player
                out, _ = kernel.call(ram, 0x109e, stop=0x111f)
                expected = queue[:]
                if game == 'laireuro':
                    expected[head], expected[end] = expected[end], expected[head]
                actual = [word(out, base - 0xa000 + 2 * i) for i in range(count)]
                if actual != expected:
                    raise ValueError('Recovery changed the queue beyond its specified swap')
                modulus = count if game == 'laireuro' else 128
                if word(out, head_at) != base + 2 * ((head + 1) % modulus):
                    raise ValueError('Unexpected recovery head')
                if word(out, end_at) != base + 2 * ((end + 1) % modulus):
                    raise ValueError('Unexpected recovery end boundary')
                cases += 1
    return cases


def italian_shuffle(kernel, rom):
    initial, _ = kernel.call(bytearray(1024), 0x1bbd)
    starts, sizes = rom[0xded:0xdf9], rom[0xdfa:0xe06]
    cases = 0
    for phase in range(128):
        out, _ = kernel.call(initial, 0x1c34, refresh=phase)
        for start, size in zip(starts, sizes):
            a = 0x300 + start
            if collections.Counter(initial[a:a + size]) != collections.Counter(out[a:a + size]):
                raise ValueError('Italian shuffle changes a pool or initial/spare slot multiset')
        _, writes = kernel.access()
        if any(i < 0x300 and i not in (0x201, 0x202, 0x203, 0x204) for i in writes):
            raise ValueError('Italian background shuffle writes outside its pools/RNG')
        cases += 1
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--roms', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    for game in ('laireuro', 'lair_ita'):
        rom = euro_tables.load(args.roms / (game + '.zip'), game)
        model = euro_optimality.Model(rom, game)
        model.verify_room_boundaries()
        graph = model.graph()
        result = rom_proof.solve(graph)
        kernel = rom_kernel.Kernel(rom, args.output / 'build')
        roots = model.data['roots'][3:]
        cases = recoveries(kernel, game, roots)
        row = dict(game=game, recovery_cases=cases, room_dispatch_boundary_checked=True,
                   rom_sha256=hashlib.sha256(rom).hexdigest())
        if game == 'lair_ita':
            row['shuffle_cases'] = italian_shuffle(kernel, rom)
            row['pools'] = model.italian_pools()
            row['initial_rooms'], row['spares'] = 12, 5
        else:
            row['root_values'] = model.totals(graph, result, roots)
        rows.append(row)
        print(game, 'recovery queue cases', cases, flush=True)
    sources = {n: hashlib.sha256((Path(__file__).parent / n).read_bytes()).hexdigest() for n in
               ('verify_euro_scheduler.py', 'euro_optimality.py', 'euro_tables.py',
                'rom_proof.py', 'rom_kernel.py', 'rom_kernel.c')}
    report = dict(all_passed=True, cases=rows, sources=sources,
                  scope='Semantic queue and room-boundary invariants; no input timing or Android runtime validation')
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
