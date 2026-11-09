#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify completion evidence, retained coverage, and the actual tables inside APKs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

ROOT = Path(__file__).resolve().parents[2]

def rows(path):
    return {game: {(int(h,16), int(o), int(f)) for h,o,f in
                    re.findall(r'\{UINT64_C\(0x([0-9a-f]+)\), (\d+), (\d+)\}', block)}
            for game,block in re.findall(r'SafeOutcome (\w+)_moves\[\] = \{(.*?)\};',path.read_text(),re.S)}

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--apk', type=Path, action='append', default=[])
a = p.parse_args()
folder = ROOT/'android/hints/campaigns'
manifest = json.loads((folder/'manifest.json').read_text())
include = ROOT/'android/app/jni/arcade_moves.inc'
baseline = ROOT/'android/hints/legacy'/manifest.get('baseline_file','arcade_moves-android8.inc')
assert hashlib.sha256(include.read_bytes()).hexdigest() == manifest['apk_include_sha256']
assert hashlib.sha256(baseline.read_bytes()).hexdigest() == manifest['baseline_sha256']
current, previous = rows(include), rows(baseline)
for game in previous:
    assert previous[game] <= current[game], 'Lost existing hint coverage: '+game
for entry in manifest['campaigns']:
    path = folder/entry['file']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256']
    data = json.loads(path.read_text()); report = data['exploration']
    if data.get('signature_schema') == 2:
        assert data['signature_header_sha256'] == hashlib.sha256((ROOT/'android/app/jni/arcade_signature.h').read_bytes()).hexdigest()
    assert report['complete'] is True and report['late_inputs'] == 0
    assert report['lives_before'] == report['lives_after'] and report['lives_before'] > 0
    assert report['completion_scope'] == 'one death-free campaign'
    for hint in data['hints']:
        assert (int(hint['headers'],16),hint['outcome'],hint['frame']) in current[data['game'] + ('_canonical' if data.get('signature_schema',1)==2 else '')]
print('Completed-campaign evidence and retained/new table coverage passed')
for apk in a.apk:
    with zipfile.ZipFile(apk) as z:
        libs = [n for n in z.namelist() if n.startswith('lib/') and n.endswith('/libmain.so')]
        assert libs, 'No emulator native library in '+str(apk)
        for lib in libs:
            blob = z.read(lib)
            # SafeOutcome is 16 bytes on every packaged little-endian ABI.
            for group in current.values():
                for h,o,f in group:
                    assert struct.pack('<QB3xI',h,o,f) in blob, f'Missing compiled hint {h:x}/{o}/{f} in {apk}:{lib}'
            print(apk.name, lib, 'contains every generated/retained hint')
