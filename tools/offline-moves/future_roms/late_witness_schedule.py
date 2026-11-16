#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compose offline physical witnesses with exact natural-checkpoint guards."""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import hashlib
import json
import os
from pathlib import Path
import subprocess

import moves

ROOT = CORE


def load(path):
    if path is None:
        return []
    row = json.loads(path.read_text())
    if not row.get('verified', row.get('all_passed', False)):
        raise ValueError('Prior witness was not independently verified')
    if hashlib.sha256((path.parent/'route.trace').read_bytes()).hexdigest() != row['trace_sha256']:
        raise ValueError('Prior physical trace changed')
    if 'anchors' in row:
        return row['anchors']
    lines = (path.parent/'input-timing.txt').read_text().splitlines()
    if lines[0] != 'HYPCADE_ROM_TIMING_V1' or len(lines) != 2:
        raise ValueError('Unsupported legacy witness schedule')
    scene, step, control, delay = map(int, lines[1].split())
    return [dict(scene=scene, step=step, control=control, delay=delay,
                 source_cycle=row['selected_event']['source_cycle'])]


def guarded(code, anchors):
    keys = [(a['scene'], a['step'], a['control']) for a in anchors]
    if len(set(keys)) != len(keys):
        raise ValueError('Repeated context requires a different schedule representation')
    for a in anchors:
        if min(a.values()) < 0:
            raise ValueError('Negative schedule field')
    old = 'p->delay>CINE_CPU_HZ'
    if code.count(old) != 1:
        raise ValueError('Schedule delay bound changed')
    code = code.replace(old, 'p->delay>4*(uint64_t)CINE_CPU_HZ')
    old = 'if(p->scene==scene && p->step==step && p->control==control) {'
    if code.count(old) != 1:
        raise ValueError('Schedule admission guard changed')
    guards = ['(scene==%d && step==%d && control==%d && m.board.cycles==UINT64_C(%d))' %
              (a['scene'], a['step'], a['control'], a['source_cycle']) for a in anchors]
    return code.replace(old, old[:-3]+' && ('+' || '.join(guards or ['false'])+')) {')


def write(path, anchors):
    path.write_text('HYPCADE_ROM_TIMING_V1\n'+''.join('%d %d %d %d\n' %
        (a['scene'], a['step'], a['control'], a['delay']) for a in anchors))


def compile_source(folder, source, observed=False):
    moves.verify_vendor()
    vendor = ROOT/'vendor/src'
    sources = [str(vendor/p) for p in moves.SOURCES if not observed or p != 'cpu/z80.c']
    if observed:
        sources.append(str(folder/'observed-z80.c'))
    binary = folder/'scheduled-player'
    subprocess.run([os.environ.get('CC', 'cc'), '-O3', '-std=c11', '-D_POSIX_C_SOURCE=200809L',
        '-Wall', '-Wextra', '-Werror', '-I'+str(ROOT), '-I'+str(vendor), str(source),
        *sources, '-lz', '-lm', '-o', str(binary)], check=True)
    return binary.resolve()


def build(folder, anchors):
    folder.mkdir(parents=True, exist_ok=True)
    source = folder/'scheduled-player.c'
    source.write_text(guarded((source_path('rom_routes.c')).read_text(), anchors))
    return compile_source(folder, source)
