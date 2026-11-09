#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate the complete-campaign sweep, then merge its hints for an APK build."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import hints

DELAYS = [0, .137, .271, .509, .887, 1.123, 1.739, 2.111]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--roms', type=Path, required=True)
    p.add_argument('--results', type=Path, required=True)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--reuse-completed', action='store_true', help='reuse only matching engine, ROM and configuration results')
    a = p.parse_args()
    a.results.mkdir(parents=True, exist_ok=True)
    files = []
    engine_hash = hashlib.sha256((hints.ROOT/'extract.c').read_bytes()).hexdigest()
    signature_hash = hashlib.sha256((hints.ROOT/'../../android/app/jni/arcade_signature.h').read_bytes()).hexdigest()
    vendor_hash = hashlib.sha256((hints.ROOT/'vendor/provenance.json').read_bytes()).hexdigest()
    jobs = [('dle21', f'dle21-{i}', 'ace', delay) for i, delay in enumerate(DELAYS)]
    jobs += [('ace', 'ace-'+skill, skill, 0) for skill in ['cadet', 'captain', 'ace']]
    for game, name, skill, delay in jobs:
        dest = a.results/(name+'.json')
        identity = hints.identity(a.roms/(game+'.zip'), game)
        reuse = False
        if a.reuse_completed and dest.exists():
            old = json.loads(dest.read_text())
            config = old.get('configuration', {})
            effective_banks = (0x32, 0xd8) if game == 'dle21' else (0x3d, 0xee)
            reuse = (old.get('signature_schema') == 2 and old.get('signature_header_sha256') == signature_hash and old.get('game') == game and old.get('engine_sha256') == engine_hash and
                     old.get('vendor_manifest_sha256') == vendor_hash and old.get('rom_chips') == identity and
                     config.get('skill') == skill and config.get('start_delay') == delay and
                     (config.get('dsw1'), config.get('dsw2')) == effective_banks and
                     old.get('exploration', {}).get('complete') is True)
        if not reuse:
            with (a.results/(name+'.log')).open('w') as log:
                subprocess.run([sys.executable, str(hints.ROOT/'hints.py'), 'extract', '--mode', 'campaign',
                                '--game', game, '--rom', str(a.roms/(game+'.zip')), '--skill', skill,
                                '--start-delay', str(delay), '--output', str(dest)],
                               stdout=log, stderr=subprocess.STDOUT, check=True)
        files.append(dest)
        print('Completed:', name, '(reused)' if reuse else '', flush=True)
    hints.compile_hints(files, a.output, a.baseline, True)
    entries = []
    for f in files:
        d = json.loads(f.read_text())
        entries.append(dict(file=f.name, sha256=hashlib.sha256(f.read_bytes()).hexdigest(),
                            game=d['game'], configuration=d['configuration'],
                            hints=len(d['hints']), completion=d['exploration']))
    manifest = dict(schema=1, completion_scope='eight DLE21 campaigns and three Ace skill campaigns; not exhaustive state-space coverage',
                    signature_schema=2, campaigns=entries, baseline_file=a.baseline.name, baseline_sha256=hashlib.sha256(a.baseline.read_bytes()).hexdigest(),
                    apk_include_sha256=hashlib.sha256(a.output.read_bytes()).hexdigest())
    hints.atomic_json(a.results/'manifest.json', manifest)

if __name__ == '__main__': main()
