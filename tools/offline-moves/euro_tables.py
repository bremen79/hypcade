#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Decode and rank European-board Dragon's Lair ROM tables.

This is a separate format from the Cinematronics compact records. No ROM bytes
are emitted into the application: only record IDs, input targets and rankings.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
import zlib
import move_arrays

LAYOUTS = {
    'lair_ita': dict(chips=(0x2ed85958,0x8479612b,0x6a66f6b4,0x0c0b3011),banks=(0xdf,0xef),per_player_difficulty=True),
    'laireuro': dict(chips=(0x4d3a9eac,0x8479612b,0x6a66f6b4,0x36575106),banks=(0x16,0xf6),per_player_difficulty=False),
}
BASE = 0x2088
RECORD_COUNT = 704
# The ROM shifts its active-low input latch through these five target slots.
SLOTS = {7: 1, 6: 2, 5: 4, 4: 8, 3: 16}


def load(path, game='lair_ita'):
    path=Path(path)
    chips=LAYOUTS[game]['chips']
    def read_chips(source, expected):
        parts = {}
        with zipfile.ZipFile(source) as archive:
            for info in archive.infolist():
                if info.CRC in expected:
                    data = archive.read(info)
                    if len(data) != 8192 or zlib.crc32(data) != info.CRC:
                        raise ValueError('Invalid European-board ROM chip')
                    if info.CRC in parts:
                        raise ValueError('Duplicate European-board ROM chip')
                    parts[info.CRC] = data
        return parts
    parts=read_chips(path,chips)
    # Identify the Italian revision from its two replacement chips before
    # consulting the European parent. Never classify the parent as Italian.
    if chips[0] not in parts or chips[3] not in parts:
        raise ValueError('Unsupported %s ROM revision' % game)
    missing=set(chips)-set(parts)
    if missing and game=='lair_ita':
        parent=path.with_name('laireuro.zip')
        if not parent.is_file():
            raise ValueError('Split Italian ROM requires laireuro.zip beside it')
        parts.update(read_chips(parent,missing))
    if set(parts) != set(chips):
        raise ValueError('Incomplete %s ROM revision' % game)
    return b''.join(parts[crc] for crc in chips)


def word(data, at):
    if not 0 <= at < len(data)-1:
        raise ValueError('Truncated European ROM table')
    return int.from_bytes(data[at:at+2], 'little')


def bcd(value):
    digits = [(value >> shift) & 15 for shift in (12, 8, 4, 0)]
    if any(d > 9 for d in digits):
        raise ValueError('Invalid packed BCD award')
    return sum(d * 10**(3-i) for i, d in enumerate(digits))


def inventory(rom, game='lair_ita'):
    if game not in LAYOUTS:
        raise ValueError('Unsupported European-board game')
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
    for target in roots:
        if target not in (0, 0xffff) and target & 0x7fff not in known:
            raise ValueError('European root outside decoded records')
    unresolved=[]
    for record in records:
        for control,target in [(0,record['default'])]+[(i['control'],i['target']) for i in record['inputs']]:
            if target not in (0,0xffff) and target & 0x7fff not in known:
                unresolved.append(dict(source=record['id'],control=control,target=target))
    result=dict(schema=1, game=game, rom_sha256=hashlib.sha256(rom).hexdigest(),
        roots=roots, records=records, all_scenes_proven=False,
        limits='Complete fixed-record inventory; local rankings do not prove global optimality or runtime reachability.')
    if unresolved:
        # Keep malformed ROM links for audit. They are not safe continuations;
        # never repair a destination by guessing which death record was intended.
        result['unresolved_targets']=unresolved
    return result


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
        rec = records.get(index)
        if rec is None:
            return None
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
    game=table['game']
    text = '/* Generated by euro_moves.py from ROM tables; no ROM payload. */\n'
    text += 'static const ArcadeEuroRule %s_rules[] = {\n' % game
    text += ''.join('    {%d,%d,%d},\n' % tuple(row) for row in table['rules'])+'};\n'
    aliases = {}
    for goal, suffix in (('shortest', 'fewest'), ('highest-score', 'max')):
        order = table['policies'][goal]; name=game+'_rules_'+suffix
        key=tuple(order)
        if key in aliases:
            text += '#define %s %s\n' % (name, aliases[key])
        else:
            text += 'static const uint16_t %s[] = {\n%s\n};\n' % (name,
                '\n'.join('    '+','.join(map(str, order[i:i+24]))+',' for i in range(0,len(order),24)))
            aliases[key]=name
    return text


def native_bundle(tables):
    source=''.join(native_include(t) for t in sorted(tables,key=lambda t:t['game']))
    source,_=move_arrays.deduplicate(source)
    source+='static const ArcadeEuroProfile arcade_euro_profiles[] = {\n'
    source+=''.join('    ARCADE_EURO_PROFILE("%s",%s,%s),\n' %
        (t['game'],t['game'],str(LAYOUTS[t['game']]['per_player_difficulty']).lower())
        for t in sorted(tables,key=lambda t:t['game']))
    return source+'};\n'


def write_bundle(folder, tables, reports):
    folder.mkdir(parents=True,exist_ok=True)
    games=sorted(t['game'] for t in tables)
    if len(set(games))!=len(games) or set(games)!={r['game'] for r in reports}:
        raise ValueError('European bundle game/evidence mismatch')
    files={}
    for table in tables:
        game=table['game'];report=next(r for r in reports if r['game']==game)
        for name,data in ((game+'-moves.json',table),(game+'-verification.json',report)):
            (folder/name).write_text(json.dumps(data,indent=2)+'\n')
            files[name]=hashlib.sha256((folder/name).read_bytes()).hexdigest()
    name='arcade_euro_moves.inc'
    (folder/name).write_text(native_bundle(tables))
    files[name]=hashlib.sha256((folder/name).read_bytes()).hexdigest()
    (folder/'manifest.json').write_text(json.dumps(dict(schema=2,games=games,files=files),indent=2)+'\n')
    verify_bundle(folder,folder/name)


def verify_bundle(folder, include):
    manifest=json.loads((folder/'manifest.json').read_text())
    if manifest['schema']!=2 or not set(manifest['games'])<=set(LAYOUTS):
        raise ValueError('Unknown European bundle schema/game')
    tables=[]
    for game in manifest['games']:
        table=json.loads((folder/(game+'-moves.json')).read_text());data=table['inventory']
        if data['game']!=game or table['game']!=game:
            raise ValueError('European bundle revision mismatch')
        planned={goal:policies(data,goal) for goal in ('shortest','highest-score')}
        expected=compact(data,planned)
        if table!=json.loads(json.dumps(expected)):
            raise ValueError('Incomplete or changed European move policies')
        tables.append(table)
        report=json.loads((folder/(game+'-verification.json')).read_text())
        if report['game']!=game or report['rom_sha256']!=data['rom_sha256']:
            raise ValueError('European replay ROM identity mismatch')
        if len(report['results'])!=report['planned'] or not report['results'] or not all(r['verified'] for r in report['results']):
            raise ValueError('European verification is incomplete')
        print('%s: %d decoded records; %d shared ranked rules; %d replayed host cases' %
            (game,len(data['records']),len(table['rules']),len(report['results'])))
    if include.read_text()!=native_bundle(tables):
        raise ValueError('Incomplete or changed European native policies')
    required={game+suffix for game in manifest['games'] for suffix in ('-moves.json','-verification.json')}|{'arcade_euro_moves.inc'}
    if set(manifest['files'])!=required:
        raise ValueError('European manifest omits required evidence')
    for name,digest in manifest['files'].items():
        path=include if name=='arcade_euro_moves.inc' else folder/name
        if Path(name).name!=name or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('European move evidence hash mismatch')


def export(rom_path, output, game='lair_ita'):
    output.mkdir(parents=True, exist_ok=True)
    data = inventory(load(rom_path,game),game)
    (output/'inventory.json').write_text(json.dumps(data, indent=2)+'\n')
    result = {}
    for goal in ('shortest', 'highest-score'):
        policy = policies(data, goal); result[goal] = policy
        write_policy(output/(goal+'.policy'), policy)
        (output/(goal+'-policy.json')).write_text(json.dumps(policy, indent=2)+'\n')
    print('[ROM] %s: %d fixed records; %d/%d ranked alternatives' %
        (game, len(data['records']), len(result['shortest']['choices']), len(result['highest-score']['choices'])), flush=True)
    return data, result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--game', choices=LAYOUTS, default='lair_ita')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export(args.rom, args.output, args.game)
