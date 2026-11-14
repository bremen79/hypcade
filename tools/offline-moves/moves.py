#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared ROM identity, vendor verification and atomic file helpers."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile
import zlib

ROOT = Path(__file__).resolve().parent
import rom_tables
CHIPS = {game: [(f'{layout["prefix"]}_u{i+1}.bin', crc)
                for i, crc in enumerate(layout['crc'])]
         for game, layout in rom_tables.LAYOUTS.items()}

SOURCES = ['../../board_adapter.c', 'cpu/z80.c', 'audio/ay8910.c',
           'ldp/ldp.c', 'ldp/ldv1000.c', 'util/roms.c', 'util/zip.c']


def verify_vendor():
    manifest = json.loads((ROOT / 'vendor/provenance.json').read_text())
    for name, digest in manifest['sha256'].items():
        if hashlib.sha256((ROOT / 'vendor' / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Vendored source checksum mismatch: ' + name)
    return manifest


def identity(rom, game):
    result = []
    with zipfile.ZipFile(rom) as archive:
        # Refuse ambiguous duplicate entries and unknown variants. ZIP packaging
        # changes do not change ROM identity: hashes cover the uncompressed chips.
        names = archive.namelist()
        folded = [n.lower() for n in names]
        for name, crc in CHIPS[game]:
            if folded.count(name) != 1:
                raise ValueError('Missing or duplicate ROM chip: ' + name)
            member = names[folded.index(name)]
            if archive.getinfo(member).file_size != 8192:
                raise ValueError('Unexpected ROM size: ' + name)
            data = archive.read(member)
            if zlib.crc32(data) != crc:
                raise ValueError('Unsupported ROM revision/checksum: ' + name)
            result.append(dict(name=name, size=len(data), crc32=f'{crc:08x}',
                               sha256=hashlib.sha256(data).hexdigest()))
        expected = {name for name, _ in CHIPS[game]}
        # Native loader searches by filenames. Restrict the input so another
        # supported set in the same ZIP cannot win its preference order.
        if any(n.lower().endswith('.bin') and n.lower() not in expected for n in archive.namelist()):
            raise ValueError('Use a ZIP containing only this ROM set (extra .bin files found)')
    return result


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as f:
        json.dump(data, f, indent=2)
        f.write('\n')
        temp = Path(f.name)
    os.replace(temp, path)


def ensure_native_catalog():
    lines=['// Generated from rom_tables.LAYOUTS; keep ROM pin data consistent.',
           'static const OfflineRom offline_roms[] = {']
    for game, layout in rom_tables.LAYOUTS.items():
        names=', '.join('"'+name+'"' for name, _ in CHIPS[game])
        crcs=', '.join('0x%08xU'%crc for _, crc in CHIPS[game])
        defaults=layout.get('dips', [0x3d,0xfe] if game=='ace' else [0x66,0x98] if game=='sae' else [0x22,0xd8])
        lines.append('    {"%s", %d, {%s}, {%s}, %s, %s, %d, %d, %d},' %
            (game,layout['chips'],names,crcs,'true' if rom_tables.space_ace(game) else 'false',
             'true' if layout.get('pr7820') else 'false',rom_tables.difficulty_count(game),*defaults))
    lines.append('};')
    path=ROOT/'rom_catalog.inc';data='\n'.join(lines)+'\n'
    if not path.exists() or path.read_text()!=data:path.write_text(data)
