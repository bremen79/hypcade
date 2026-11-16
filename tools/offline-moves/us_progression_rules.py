#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A–D surviving-room progression and full raw-hard selector entry contracts.

Ordinary/optional rooms advance one group; the two fixed intermissions return
to one and the final dragon wins. Death/queued restart composition is separate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

import cine_room_optimality
import dl1_selector
import late_retry_rules
import rom_kernel
import rom_proof
import rom_tables
import verify_dl1_scheduler

ROOT = Path(__file__).resolve().parent
ADVANCE = bytes.fromhex('3a12a0cb7fc8fdcb054ec0210600197e3cf6803212a0')
ASSIGN = bytes.fromhex('2112a07ecb7f280d2e0e772e0f36002108a0cb86c92e0f772e0efd7e0277c9')
FRESH = bytes.fromhex('3a10a0cb5fc03a12a0cb7fc821050019cb6ec0e67f3254a021060019772bcb7e2805cb762001c9')


def audit(rom, game, saved, build):
    advance = rom.find(ADVANCE)
    fresh = rom.find(FRESH)
    if advance < 0 or fresh < 0 or rom[advance+22] != 0xcd or rom[advance+25] != 0xc9:
        raise ValueError('Unrecognized original progression routines')
    assign = rom_tables.word(rom, advance+23)
    if rom[assign:assign+len(ASSIGN)] != ASSIGN:
        raise ValueError('Advance calls a different record assignment rule')
    kernel = rom_kernel.Kernel(rom, build)
    advance_cases = 0
    def check(raw, flags, group, player, fill):
        nonlocal advance_cases
        ram = bytearray([fill]*1024)
        ram[18] = raw
        ram[0x205] = flags
        ram[player+6] = group
        expected = late_retry_rules.advance(ram, player)
        actual, regs = kernel.call(ram, advance, de=0xa000+player, refresh=127)
        if actual[:0x3d0] != expected[:0x3d0] or regs['observations']:
            raise ValueError('Original A–D advance differs from the declared rule')
        reads, writes = kernel.access()
        active = raw & 128 and not flags & 2
        allowed_reads = {18} | ({0x205} if raw & 128 else set()) | ({player+6, 8} if active else set())
        allowed_writes = {18, 14, 15, 8} if active else set()
        if {i for i in reads if i < 0x3d0} != allowed_reads or {i for i in writes if i < 0x3d0} != allowed_writes:
            raise ValueError('Advance reads or writes undeclared progression state')
        advance_cases += 1
    for player in (0x30, 0x38):
        for raw in range(256):
            for flags in (0, 2, 253, 255):
                check(raw, flags, 12, player, 37)
        for group in range(256):
            for fill in (0, 255):
                check(128, 0, group, player, fill)
    desc = verify_dl1_scheduler.descriptors(rom, game)
    if any(d['flags'] != (10 if g == 13 else 2) or d['mask'] != 7 for g, d in desc.items()):
        raise ValueError('Three-pass descriptors changed')
    model = cine_room_optimality.Model(rom, game)
    graph = model.graph()
    index = {s: u for u, s in enumerate(graph['states'])}
    ordinary = {s+40 for g, d in desc.items() if g < 13 for s in d['scenes']} | set(range(80, 85))
    final = [s+40 for s in desc[13]['scenes'][::-1]]
    if final != [60, 70, 76]:
        raise ValueError('Unrecognized final intermission/dragon order')
    effects, _ = verify_dl1_scheduler.room_effects(model, graph, ordinary | set(final))
    for scene in ordinary:
        if effects[index[scene, 0]] != {('next',)}:
            raise ValueError('A selectable room can change the ordinary itinerary')
    for scene, expected in ((60, {('explicit', 1)}), (70, {('explicit', 1)}), (76, {('win',)})):
        if effects[index[scene, 0]] != expected:
            raise ValueError('Final room has an unexpected surviving exit')
    table_row = next(t for t in saved['selector_tables'] if t['raw_hard'] and t['hard'])
    support = {(r['used'], r['mask']): {tuple(v) for v, _ in r['support']} for r in table_row['rows']}
    selector_cases = 0
    for group in range(1, 14):
        for mask in ((0, 4, 6) if group == 13 else range(7)):
            for used in range(32):
                for seed in range(8):
                    ram = bytearray(1024)
                    ram[16], ram[17], ram[18], ram[0x35] = 4, 0x18, 128 | group, 16
                    ram[0x60+group] = mask
                    for i in range(5):
                        ram[0x70+i] = 128 if used & (1 << i) else 0
                    out, _ = kernel.call(ram, fresh, refresh=seed)
                    at = dl1_selector.descriptor_base(rom)+4*group
                    if out[0x36] != group or out[0x54] != group or out[0x50:0x54] != rom[at:at+4] or out[15] != 0:
                        raise ValueError('Full entry does not install the logical group/ROM descriptor')
                    if group == 13:
                        lap = (0, 4, 6).index(mask)
                        actual_used = sum(bool(out[0x70+i]) << i for i in range(5))
                        if out[14] & 127 != final[lap] or out[0x6d] != (4, 6, 7)[lap] or actual_used != used:
                            raise ValueError('Final selector changed order, history or optional resources')
                    else:
                        value = dl1_selector.decode(rom, game, group, mask, used, out, True, True)
                        if value not in support[used, mask]:
                            raise ValueError('Full selector entry escapes the complete extracted support')
                    selector_cases += 1
    return dict(game=game, advance_pc=advance, fresh_selector_pc=fresh,
        native_advance_cases=advance_cases, native_fresh_selector_cases=selector_cases,
        ordinary_roots=sorted(ordinary), final_order=final,
        itinerary='Every surviving ordinary or optional completion advances one group; final descending masks 0/4/6 select return-to-one, return-to-one, win',
        scope='Canonical raw-hard single-player surviving progression and room-boundary roles. Queued/death dispatch and arbitrary-clock controllability remain separate.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--roms', type=Path, required=True)
    p.add_argument('--selectors', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    cached = json.loads(a.selectors.read_text())
    for name, expected in cached['sources'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Selector evidence source changed: '+name)
    cases = []
    for game in ('lair_a', 'lair_b', 'lair_c', 'lair_d'):
        rom = rom_tables.load(a.roms/(game+'.zip'), game)
        saved = next(r for r in cached['cases'] if r['game'] == game)
        if hashlib.sha256(rom).hexdigest() != saved['rom_sha256']:
            raise ValueError('Selector evidence ROM changed')
        cases.append(audit(rom, game, saved, a.output/'build'/game))
        print(game, cases[-1]['native_advance_cases'], cases[-1]['native_fresh_selector_cases'], flush=True)
    result = dict(cases=cases, all_passed=True, seconds=time.monotonic()-started,
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        selectors_sha256=hashlib.sha256(a.selectors.read_bytes()).hexdigest(),
        sources={n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in
            ('us_progression_rules.py', 'late_retry_rules.py', 'verify_dl1_scheduler.py', 'cine_room_optimality.py',
             'dl1_selector.py', 'rom_tables.py', 'rom_proof.py', 'rom_kernel.py', 'rom_kernel.c')})
    (a.output/'report.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
