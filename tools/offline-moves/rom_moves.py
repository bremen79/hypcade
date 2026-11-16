#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the original-CPU policy player and read its physical replay records."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

import moves as move_tools
import rom_tables
import score_routes

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]


def identity():
    result=score_routes.source_identity()
    for name in ('rom_tables.py','rom_routes.c','rom_moves.py','moves.py'):
        p=ROOT/name;result[str(p.relative_to(REPO))]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def build(folder):
    folder.mkdir(parents=True,exist_ok=True);binary=folder/'rom-routes';stamp=folder/'sources.json';tag=identity()
    if binary.exists() and stamp.exists() and json.loads(stamp.read_text())==tag:return binary
    move_tools.verify_vendor();src=ROOT/'vendor/src';staged=folder/'rom-routes.staged'
    print('[build] ROM table player; original CPU and player; no video/audio/waits',flush=True)
    subprocess.run([os.environ.get('CC','cc'),'-O3','-std=c11','-D_POSIX_C_SOURCE=200809L',
                    '-Wall','-Wextra','-Werror','-I'+str(src),str(ROOT/'rom_routes.c'),
                    *[str(src/p) for p in move_tools.SOURCES],'-lz','-lm','-o',str(staged)],check=True)
    if identity()!=tag:raise ValueError('Sources changed during build')
    staged.replace(binary);move_tools.atomic_json(stamp,tag);return binary


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.startswith('{')]
