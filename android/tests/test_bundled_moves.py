#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the ROM-state move sets and their complete replay evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"tools/offline-moves"))
import export_rom_moves
import rom_tables
import euro_tables
from bundle_rom_moves import runtime_policy, rule_coverage

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apk',type=Path,action='append',default=[])
    parser.add_argument('--roms',type=Path,help='Also re-decode the supplied ROM ZIPs to verify inventory authenticity');parser.add_argument('--bundle-dir',type=Path,help='Check a directly generated extraction output instead of the bundled APK inputs')
    args=parser.parse_args()
    if not args.bundle_dir:
        euro_tables.verify_bundle(ROOT/'android/moves/euro-tables',ROOT/'android/app/jni/arcade_euro_moves.inc')
    euro_table=json.loads((ROOT/'android/moves/euro-tables/lair_ita-moves.json').read_text()) if not args.bundle_dir else None
    folder=args.bundle_dir or ROOT/'android/moves/rom-tables';manifest=json.loads((folder/'manifest.json').read_text())
    include=folder/'arcade_moves.inc' if args.bundle_dir else ROOT/'android/app/jni/arcade_moves.inc';source=include.read_text()
    assert hashlib.sha256(include.read_bytes()).hexdigest()==manifest['apk_include_sha256']
    assert manifest['profiles']
    games=set(manifest['counts'])
    assert games and games <= set(rom_tables.LAYOUTS)
    assert {(p['game'],p['objective']) for p in manifest['profiles']}=={(g,o) for g in games for o in ('shortest','highest-score')}
    settings={(p['game'],p['skill'],p['difficulty']) for p in manifest['profiles']}
    expected_settings=set()
    for game in games:
        skills=rom_tables.skills(game)
        levels=range(rom_tables.difficulty_count(game))
        expected_settings.update((game,s,d) for s in skills for d in levels)
    assert settings==expected_settings
    for name,digest in manifest['files'].items():assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest,name
    assert manifest['schema']==4
    pools={name:[tuple(map(int,row)) for row in re.findall(r'\{(\d+)U, (\d+)U, (\d+), (\d+), (\d+)\}',body)]
            for name,body in re.findall(r'ArcadeRomMove (\w+)\[\] = \{(.*?)\};',source,re.S)}
    rule_pools={name:[tuple(map(int,row)) for row in re.findall(r'\{(\d+), (\d+), (\d+), (\d+)\}',body)]
                for name,body in re.findall(r'ArcadeRomRule (\w+)\[\] = \{(.*?)\};',source,re.S)}
    orders={name:list(map(int,re.findall(r'\d+',body)))
            for name,body in re.findall(r'uint16_t (\w+)\[\] = \{(.*?)\};',source,re.S)}
    # Aliases share storage; reconstruct their semantic view for coverage checks.
    pending=dict(re.findall(r'^#define (\w+) (\w+)\s*$',source,re.M))
    while pending:
        before=len(pending)
        for name,target in list(pending.items()):
            for tables in (pools,rule_pools,orders):
                if target in tables:
                    tables[name]=tables[target];del pending[name];break
        assert len(pending)<before, 'Unknown or cyclic move-array alias'
    assert set(rule_pools)=={g+'_rules' for g in games}
    assert set(pools)=={g+'_moves' for g in games}
    arrays={}
    for game in sorted(games):
        pool=pools[game+'_moves']
        assert pool==sorted(set(pool)) and len(pool)<=65536
        assert len(pool)==manifest['shared_counts'][game]
        table=json.loads((folder/(game+'-moves.json')).read_text())
        assert set(table)=={'moves','policies','rules','native_rules','rule_policies'}
        # Reconstruct the entire expected export, independently of sampled plays.
        # Omitting a rule (even after rehashing files) must fail this equality.
        inventory=json.loads((folder/(game+'-inventory.json')).read_text())
        if args.roms:
            assert rom_tables.inventory(rom_tables.load(args.roms/(game+'.zip'),game),game)==inventory
        policies={goal:rom_tables.policies(inventory,goal) for goal in export_rom_moves.OBJECTIVES}
        expected=export_rom_moves.compile_rules(inventory,policies)
        assert table['rules']==expected, 'Decoded ROM windows were omitted or changed'
        native,rule_orders=runtime_policy(expected)
        assert native==rule_pools[game+'_rules']
        assert table['native_rules']==[dict(state=r[0],window=r[1],outcome=r[2],control=r[3]) for r in native]
        assert table['rule_policies']==rule_orders
        for goal,suffix in (('shortest','fewest'),('highest-score','max')):
            assert orders[game+'_rules_'+suffix]==rule_orders[goal], 'Missing ranked ROM alternative'
        declared=manifest['rom_coverage'][game]
        assert all(declared[k]==v for k,v in rule_coverage(inventory,expected,native,rule_orders).items())
        assert declared['decoded_rules']==declared['retained_rules']==len(expected)
        assert declared['ranked_rules']==sum(bool(r['objectives']) for r in expected)
        assert declared['runtime_rules']==len(native)
        print('%s: %d/%d decoded rules retained; %d/%d ranked choices represented in runtime policies'%
              (game,len(expected),len(expected),declared['ranked_rules'],declared['ranked_rules']))
        assert set(table['policies'])=={'shortest','highest-score'}
        assert pool==[tuple(r[k] for k in ('state','frame','timing','outcome','control')) for r in table['moves']]
        used=set()
        for objective,suffix in (('shortest','fewest'),('highest-score','max')):
            name=game+'_moves_'+suffix;order=orders[name]
            assert order==table['policies'][objective]
            assert len(order)==len(set(order)) and all(0<=i<len(pool) for i in order)
            used.update(order);arrays[name]=[pool[i] for i in order]
        assert used==set(range(len(pool))), 'Unreferenced move in shared pool'
    assert set(arrays)=={g+'_moves_'+suffix for g in games for suffix in ('max','fewest')}
    for name,rows in arrays.items():
        assert rows and [r[0] for r in rows]==sorted(r[0] for r in rows)
        assert all(r[4] in (1,2,4,8,16) and 0<r[1]<100000 and r[2]&255 for r in rows)
        game=name.rsplit('_moves_',1)[0]
        objective='shortest' if name.endswith('fewest') else 'highest-score'
        assert len(rows)==manifest['counts'][game][objective]
    for game in sorted(games):
        sets={o:{r[0] for r in arrays[game+'_moves_'+suffix]}
              for o,suffix in (('shortest','fewest'),('highest-score','max'))}
        known=sets['shortest']|sets['highest-score']
        coverage=manifest['calibration_coverage'][game]
        assert len(known)==coverage['known_states']
        for objective,states in sets.items():
            declared=coverage['objectives'][objective]
            waiting=set(declared['waiting_states'])
            assert not states&waiting
            assert states|waiting==known, 'A verified alternate branch lost guidance'
            assert len(states)==declared['action_states']
    for profile in manifest['profiles']:
        route=folder/profile['directory']/'route.json'
        assert route.resolve().is_relative_to(folder.resolve())
        data=json.loads(route.read_text());assert data['complete'] and data['no_life_loss'] and data['replay']['verified']
        assert data['configuration']['difficulty']==profile['difficulty']
        assert len(data['moves'])==data['replay']['move_count']==profile['moves']
        if profile['game']=='ace':
            assert any(m['control']==1 and 32570<=m['frame']<=32590 and m['score_before']==m['score_after'] for m in data['moves']),'Missing required zero-score final UP'
    for apk in args.apk:
        with zipfile.ZipFile(apk) as archive:
            libs=[n for n in archive.namelist() if n.endswith('/libmain.so')];assert libs
            for lib in libs:
                blob=archive.read(lib)
                if euro_table:
                    assert b''.join(struct.pack('<HHBx',*row) for row in euro_table['rules']) in blob,(apk,lib,'Italian rule pool')
                    for order in euro_table['policies'].values():
                        assert struct.pack('<'+'H'*len(order),*order) in blob,(apk,lib,'Italian strategy')
                for name,rows in pools.items():
                    assert b''.join(struct.pack('<IIHBB',*row) for row in rows) in blob,(apk,lib,name)
                for rows in rule_pools.values():
                    assert b''.join(struct.pack('<HBBBx',*row) for row in rows) in blob,(apk,lib,'Cine rule pool')
                for name,order in orders.items():
                    assert struct.pack('<'+'H'*len(order),*order) in blob,(apk,lib,name)
    print('Bundled moves: both objectives, %d complete replays, shared pools, policy indices and Space Ace final UP passed'%len(manifest['profiles']))

if __name__=='__main__':main()
