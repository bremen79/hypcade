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
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apk',type=Path,action='append',default=[]);args=parser.parse_args()
    folder=ROOT/'android/moves/rom-tables';manifest=json.loads((folder/'manifest.json').read_text())
    include=ROOT/'android/app/jni/arcade_moves.inc';source=include.read_text()
    assert hashlib.sha256(include.read_bytes()).hexdigest()==manifest['apk_include_sha256']
    assert manifest['profiles']
    assert {(p['game'],p['objective']) for p in manifest['profiles']}=={(g,o) for g in ('dle21','ace') for o in ('shortest','highest-score')}
    for name,digest in manifest['files'].items():assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest,name
    arrays={name:[tuple(map(int,row)) for row in re.findall(r'\{(\d+)U, (\d+)U, (\d+), (\d+), (\d+)\}',body)]
            for name,body in re.findall(r'ArcadeRomMove (\w+)\[\] = \{(.*?)\};',source,re.S)}
    assert set(arrays)=={'dle21_moves_max','dle21_moves_fewest','ace_moves_max','ace_moves_fewest'}
    for name,rows in arrays.items():
        assert rows and [r[0] for r in rows]==sorted(r[0] for r in rows)
        assert all(r[4] in (1,2,4,8,16) and 0<r[1]<100000 and r[2]&255 for r in rows)
    for profile in manifest['profiles']:
        route=folder/profile['game']/('%s-%02d'%(profile['skill'],profile['start']))/profile['objective']/'route.json'
        data=json.loads(route.read_text());assert data['complete'] and data['no_life_loss'] and data['replay']['verified']
        assert len(data['moves'])==data['replay']['move_count']==profile['moves']
        if profile['game']=='ace':
            assert any(m['control']==1 and 32570<=m['frame']<=32590 and m['score_before']==m['score_after'] for m in data['moves']),'Missing required zero-score final UP'
    for apk in args.apk:
        with zipfile.ZipFile(apk) as archive:
            libs=[n for n in archive.namelist() if n.endswith('/libmain.so')];assert libs
            for lib in libs:
                blob=archive.read(lib)
                for name,rows in arrays.items():
                    for row in rows:assert struct.pack('<IIHBB',*row) in blob,(apk,lib,name,row)
    print('Bundled moves: both objectives, %d complete replays, compact rows and Space Ace final UP passed'%len(manifest['profiles']))

if __name__=='__main__':main()
