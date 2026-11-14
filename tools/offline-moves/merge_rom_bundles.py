#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Combine disjoint verified game bundles, preserving their original evidence.

This does not relabel old replays as runs of the current generator. Each
source manifest and generation report retains its own source fingerprints.
The result uses the same shared-pool format as a single full matrix export.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import rom_tables
import move_arrays

REPO = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def merge(inputs, output):
    output = output.resolve()
    if output.exists():
        raise ValueError('Choose a new output directory')
    for folder in inputs:
        subprocess.run([sys.executable, str(REPO / 'android/tests/test_bundled_moves.py'),
                        '--bundle-dir', str(folder)], check=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='rom-bundle-stage-', dir=output.parent))
    try:
        combined = dict(schema=4, method='Verified game bundles with original per-game replay evidence',
                        profiles=[], files={}, source_bundles={}, all_scenes_proven=False,
                        global_optimum_proven=False,
                        limits='Complete decoded policies; sampled replays do not prove all reachable contexts or global optimality.')
        fields = ('counts', 'shared_counts', 'rom_coverage', 'calibration_coverage')
        for field in fields:
            combined[field] = {}
        includes = []
        for folder in inputs:
            manifest = json.loads((folder / 'manifest.json').read_text())
            games = set(manifest['counts'])
            if games & set(combined['counts']):
                raise ValueError('Duplicate game bundle')
            label = '-'.join(sorted(games))
            for field in fields:
                combined[field].update(manifest[field])
            combined['profiles'].extend(manifest['profiles'])
            combined['source_bundles'][label] = digest(folder / 'manifest.json')
            provenance = label + '-source-manifest.json'
            shutil.copyfile(folder / 'manifest.json', stage / provenance)
            combined['files'][provenance] = digest(stage / provenance)
            for name, checksum in manifest['files'].items():
                relative = Path(name)
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('File outside source bundle')
                # Root-level evidence is namespaced; game directories and
                # GAME-moves/inventory files keep their existing names.
                target_name = label + '-' + name if name == 'generation-verification.json' else name
                if target_name in combined['files']:
                    raise ValueError('Conflicting bundle file: ' + target_name)
                target = stage / target_name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(folder / relative, target)
                if digest(target) != checksum:
                    raise ValueError('Source changed while copying: ' + name)
                combined['files'][target_name] = checksum
            includes.append(re.sub(r'static const ArcadeCineProfile arcade_cine_profiles\[\] = \{.*?\};\n',
                                   '',(folder / 'arcade_moves.inc').read_text(),flags=re.S))
        includes.append('static const ArcadeCineProfile arcade_cine_profiles[] = {\n' +
                        ''.join('    ARCADE_CINE_PROFILE("%s", %s, %s),\n' %
                                (game,game,'true' if rom_tables.space_ace(game) else 'false')
                                for game in sorted(combined['counts'])) + '};\n')
        source,aliases=move_arrays.deduplicate('\n'.join(includes))
        (stage / 'arcade_moves.inc').write_text(source)
        combined['array_aliases']=aliases
        combined['apk_include_sha256'] = digest(stage / 'arcade_moves.inc')
        combined['merger_sha256'] = digest(Path(__file__))
        (stage / 'manifest.json').write_text(json.dumps(combined, indent=2) + '\n')
        subprocess.run([sys.executable, str(REPO / 'android/tests/test_bundled_moves.py'),
                        '--bundle-dir', str(stage)], check=True)
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, action='append', required=True,
                        help='Verified bundle directory; repeat for each input')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    merge(args.input, args.output)
