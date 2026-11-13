#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the two ROM-state move sets and their complete replay evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apk',type=Path,action='append',default=[])
    parser.add_argument('--bundle-dir',type=Path,help='Check a directly generated extraction output instead of the bundled APK inputs')
    args=parser.parse_args()
    folder=args.bundle_dir or ROOT/'android/moves/rom-tables';manifest=json.loads((folder/'manifest.json').read_text())
    include=folder/'arcade_moves.inc' if args.bundle_dir else ROOT/'android/app/jni/arcade_moves.inc';source=include.read_text()
    assert hashlib.sha256(include.read_bytes()).hexdigest()==manifest['apk_include_sha256']
    assert manifest['profiles']
    assert {(p['game'],p['objective']) for p in manifest['profiles']}=={(g,o) for g in ('dle21','ace') for o in ('shortest','highest-score')}
    settings={(p['game'],p['skill'],p['difficulty']) for p in manifest['profiles']}
    assert settings=={('dle21','ace',0)} | {('ace',s,d) for s in ('cadet','captain','ace') for d in range(4)}
    for name,digest in manifest['files'].items():assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest,name
    assert manifest['schema']==3
    pools={name:[tuple(map(int,row)) for row in re.findall(r'\{(\d+)U, (\d+)U, (\d+), (\d+), (\d+)\}',body)]
            for name,body in re.findall(r'ArcadeRomMove (\w+)\[\] = \{(.*?)\};',source,re.S)}
    assert set(pools)=={'dle21_moves','ace_moves'}
    orders={name:list(map(int,re.findall(r'\d+',body)))
            for name,body in re.findall(r'uint16_t (\w+)\[\] = \{(.*?)\};',source,re.S)}
    arrays={}
    for game in ('dle21','ace'):
        pool=pools[game+'_moves']
        assert pool==sorted(set(pool)) and len(pool)<=65536
        assert len(pool)==manifest['shared_counts'][game]
        table=json.loads((folder/(game+'-moves.json')).read_text())
        assert set(table)=={'moves','policies'}
        assert set(table['policies'])=={'shortest','highest-score'}
        assert pool==[tuple(r[k] for k in ('state','frame','timing','outcome','control')) for r in table['moves']]
        used=set()
        for objective,suffix in (('shortest','fewest'),('highest-score','max')):
            name=game+'_moves_'+suffix;order=orders[name]
            assert order==table['policies'][objective]
            assert len(order)==len(set(order)) and all(0<=i<len(pool) for i in order)
            used.update(order);arrays[name]=[pool[i] for i in order]
        assert used==set(range(len(pool))), 'Unreferenced move in shared pool'
    assert set(arrays)=={'dle21_moves_max','dle21_moves_fewest','ace_moves_max','ace_moves_fewest'}
    for name,rows in arrays.items():
        assert rows and [r[0] for r in rows]==sorted(r[0] for r in rows)
        assert all(r[4] in (1,2,4,8,16) and 0<r[1]<100000 and r[2]&255 for r in rows)
        game='dle21' if name.startswith('dle21') else 'ace'
        objective='shortest' if name.endswith('fewest') else 'highest-score'
        assert len(rows)==manifest['counts'][game][objective]
    for game in ('dle21','ace'):
        sets={o:{r[0] for r in arrays[game+'_moves_'+suffix]}
              for o,suffix in (('shortest','fewest'),('highest-score','max'))}
        known=sets['shortest']|sets['highest-score']
        coverage=manifest['branch_coverage'][game]
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
                for name,rows in pools.items():
                    for row in rows:assert struct.pack('<IIHBB',*row) in blob,(apk,lib,name,row)
                for name,order in orders.items():
                    assert struct.pack('<'+'H'*len(order),*order) in blob,(apk,lib,name)
    print('Bundled moves: both objectives, %d complete replays, shared pools, policy indices and Space Ace final UP passed'%len(manifest['profiles']))

if __name__=='__main__':main()
