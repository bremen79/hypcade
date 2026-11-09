#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional deterministic integration test using supplied ROMs; never distributes them."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--roms', type=Path, required=True)
a = p.parse_args()
program = Path(__file__).with_name('hints.py')
with tempfile.TemporaryDirectory(prefix='hint-replay-') as tmp:
    output = Path(tmp)
    for game in ['dle21', 'ace']:
        rom = a.roms / (game+'.zip')
        before = hashlib.sha256(rom.read_bytes()).hexdigest()
        docs = []
        for i in range(2):
            dest = output/f'{game}-{i}.json'
            subprocess.run([sys.executable, str(program), 'extract', '--game', game,
                            '--rom', str(rom), '--mode', 'explore', '--nodes', '2', '--output', str(dest)], check=True)
            doc = json.loads(dest.read_text())
            del doc['exploration']['wall_seconds']
            assert doc['hints'] and doc['exploration']['trials'] > 0
            assert doc['exploration']['complete'] is False
            docs.append(doc)
        assert docs[0] == docs[1], f'Non-deterministic evidence: {game}'
        assert hashlib.sha256(rom.read_bytes()).hexdigest() == before, 'ROM was modified'
        print(game, 'repeatability and unchanged ROM passed', flush=True)
