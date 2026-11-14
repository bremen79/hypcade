#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Decode and rank the Italian European-board Dragon's Lair ROM tables.

This is a separate format from the Cinematronics compact records. No ROM bytes
are emitted into the application: only record IDs, input targets and rankings.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
import zlib

CHIPS = (0x2ed85958, 0x8479612b, 0x6a66f6b4, 0x0c0b3011)
BASE = 0x2088
RECORD_COUNT = 704
# The ROM shifts its active-low input latch through these five target slots.
SLOTS = {7: 1, 6: 2, 5: 4, 4: 8, 3: 16}


def load(path):
    with zipfile.ZipFile(path) as archive:
        parts = {}
        for info in archive.infolist():
            if info.CRC in CHIPS:
                data = archive.read(info)
                if len(data) != 8192 or zlib.crc32(data) != info.CRC:
                    raise ValueError('Invalid Italian ROM chip')
                if info.CRC in parts:
                    raise ValueError('Duplicate Italian ROM chip')
                parts[info.CRC] = data
    if set(parts) != set(CHIPS):
        raise ValueError('Unsupported Italian ROM revision')
    return b''.join(parts[crc] for crc in CHIPS)


def word(data, at):
    if not 0 <= at < len(data)-1:
        raise ValueError('Truncated European ROM table')
    return int.from_bytes(data[at:at+2], 'little')


def bcd(value):
    digits = [(value >> shift) & 15 for shift in (12, 8, 4, 0)]
    if any(d > 9 for d in digits):
        raise ValueError('Invalid packed BCD award')
    return sum(d * 10**(3-i) for i, d in enumerate(digits))


def inventory(rom):
    if len(rom) != 32768:
        raise ValueError('Expected four 8 KiB program chips')
    rooms = word(rom, 0x2000)
    if rooms != 36:
        raise ValueError('Unexpected European room queue')
    roots = [word(rom, 0x2002+2*i) for i in range(rooms+3)]
    records = []
    for index in range(1, RECORD_COUNT+1):
        at = BASE+(index-1)*32
        payload = rom[at:at+32]
        if payload == b'\xff'*32:
            continue
        targets = [word(payload, 6+2*i) for i in range(12)]
        if any(t != 0xffff for slot, t in enumerate(targets) if slot not in SLOTS):
            raise ValueError('Unmapped European input slot')
        records.append(dict(id=index, frame=word(payload, 0), flags=payload[2],
            duration=payload[3], award=bcd(word(payload, 4)),
            death=bool(payload[2] & 16), victory=bool(payload[2] & 64),
            default=word(payload, 30), inputs=[dict(slot=slot, control=SLOTS[slot], target=target)
                for slot, target in enumerate(targets) if target != 0xffff]))
    known = {r['id'] for r in records}
    for target in roots+[t for r in records for t in [r['default']]+[i['target'] for i in r['inputs']]]:
        if target not in (0, 0xffff) and target & 0x7fff not in known:
            raise ValueError('European target outside decoded records')
    return dict(schema=1, game='lair_ita', rom_sha256=hashlib.sha256(rom).hexdigest(),
        roots=roots, records=records, all_scenes_proven=False,
        limits='Complete fixed-record inventory; local rankings do not prove global optimality or runtime reachability.')


def policies(data, objective):
    if objective not in ('shortest', 'highest-score'):
        raise ValueError('Unknown objective')
    records = {r['id']: r for r in data['records']}
    memo = {}; ranked = {}; cycles = set()
    def solve(index, active):
        if index == 0:
            return (0, 0)  # Original ROM dispatches the next room.
        if index in memo:
            return memo[index]
        if index in active:
            cycles.add(index)
            return None
        rec = records[index]
        if rec['death'] or index < data['roots'][0]:
            return None
        if rec['victory']:
            memo[index] = (0, rec['award'])
            return memo[index]
        choices = [(0, rec['default'])]+[(i['control'], i['target']) for i in rec['inputs']]
        options = []
        for control, raw in choices:
            if raw == 0xffff:
                continue
            continuation = solve(raw & 0x7fff, active | {index})
            if continuation is None:
                continue
            moves, score = continuation
            options.append(dict(id=index, control=control, target=raw,
                remaining_moves=moves+bool(control), remaining_score=score+rec['award']))
        def key(c):
            m, s = c['remaining_moves'], c['remaining_score']
            return ((m, -s) if objective == 'shortest' else (-s, m))+(c['control'], c['target'])
        options.sort(key=key)
        # Keep every safe alternative, but render/execute only the first choice.
        for rank, choice in enumerate(options):
            choice['rank'] = rank
        ranked[index] = options
        memo[index] = (options[0]['remaining_moves'], options[0]['remaining_score']) if options else None
        return memo[index]
    for index in records:
        solve(index, set())
    if cycles:
        raise ValueError('European graph contains a cycle; needs a cycle-aware planner')
    return dict(objective=objective, choices=[c for i in sorted(ranked) for c in ranked[i]],
        covered_records=len(ranked), all_scenes_proven=False, global_optimum_proven=False)


def write_policy(path, policy):
    path.write_text('HYPCADE_EURO_POLICY_V1\n'+''.join(
        '{id} {control} {target} {rank}\n'.format(**c) for c in policy['choices']))


def compact(data, policies):
    rows = sorted({(c['id'], c['target'], c['control'])
        for p in policies.values() for c in p['choices']})
    if len(rows) >= 65536:
        raise ValueError('European move pool exceeds index capacity')
    indices = {row: i for i, row in enumerate(rows)}
    orders = {goal: [indices[(c['id'], c['target'], c['control'])] for c in p['choices']]
        for goal, p in policies.items()}
    return dict(game=data['game'], inventory=data, rules=rows, policies=orders)


def native_include(table):
    text = '/* Generated by euro_moves.py from ROM tables; no ROM payload. */\n'
    text += 'static const ArcadeEuroRule lair_ita_rules[] = {\n'
    text += ''.join('    {%d,%d,%d},\n' % tuple(row) for row in table['rules'])+'};\n'
    aliases = {}
    for goal, suffix in (('shortest', 'fewest'), ('highest-score', 'max')):
        order = table['policies'][goal]; name='lair_ita_rules_'+suffix
        key=tuple(order)
        if key in aliases:
            text += '#define %s %s\n' % (name, aliases[key])
        else:
            text += 'static const uint16_t %s[] = {\n%s\n};\n' % (name,
                '\n'.join('    '+','.join(map(str, order[i:i+24]))+',' for i in range(0,len(order),24)))
            aliases[key]=name
    return text


def verify_bundle(folder, include):
    table = json.loads((folder/'lair_ita-moves.json').read_text())
    data = table['inventory']
    planned = {goal: policies(data, goal) for goal in ('shortest', 'highest-score')}
    expected = compact(data, planned)
    # JSON roundtrip normalizes tuple rows, without relaxing any comparisons.
    if table != json.loads(json.dumps(expected)) or include.read_text() != native_include(expected):
        raise ValueError('Incomplete or changed European move policies')
    manifest = json.loads((folder/'manifest.json').read_text())
    for name, digest in manifest['files'].items():
        path=include if name=='arcade_euro_moves.inc' else folder/name
        if Path(name).name != name or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('European move evidence hash mismatch')
    report = json.loads((folder/'verification.json').read_text())
    if len(report['results'])!=report['planned'] or not report['results'] or not all(r['verified'] for r in report['results']):
        raise ValueError('European verification is incomplete')
    print('lair_ita: %d decoded records; %d shared ranked rules; %d replayed host cases' %
        (len(data['records']),len(table['rules']),len(report['results'])))


def export(rom_path, output):
    output.mkdir(parents=True, exist_ok=True)
    data = inventory(load(rom_path))
    (output/'inventory.json').write_text(json.dumps(data, indent=2)+'\n')
    result = {}
    for goal in ('shortest', 'highest-score'):
        policy = policies(data, goal); result[goal] = policy
        write_policy(output/(goal+'.policy'), policy)
        (output/(goal+'-policy.json')).write_text(json.dumps(policy, indent=2)+'\n')
    print('[ROM] lair_ita: %d fixed records; %d/%d ranked alternatives' %
        (len(data['records']), len(result['shortest']['choices']), len(result['highest-score']['choices'])), flush=True)
    return data, result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export(args.rom, args.output)
