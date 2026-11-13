#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build and invoke the exact replay verifier used by the ROM-table player."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import moves as move_tools

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def source_identity():
    paths = [ROOT/name for name in ('score_routes.c', 'score_trial.h', 'score_routes.py',
             'simulation.c', 'moves.py', 'vendor/provenance.json')]
    paths += [REPO/'android/app/jni'/name for name in ('arcade_signature.h', 'arcade_move_policy.h')]
    return {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def build(directory=None):
    move_tools.verify_vendor()
    directory = Path(directory or REPO/'local-tools/offline-moves-build').resolve()
    directory.mkdir(parents=True, exist_ok=True)
    binary = directory/'score-routes'
    manifest = directory/'sources.json'
    identity = source_identity()
    if binary.is_file() and manifest.is_file() and json.loads(manifest.read_text()) == identity:
        return binary
    src=ROOT/'vendor/src'
    staged=directory/'score-routes.staged'
    print('[build] Compiling exact replay verifier; no video, audio or real-time waits',flush=True)
    # This executable stays on the build laptop. Disable FP contraction so
    # host CPU specialization cannot change the recorded player-clock hashes.
    subprocess.run([os.environ.get('CC','cc'),'-O3','-flto','-march=native','-ffp-contract=off','-std=c11','-D_POSIX_C_SOURCE=200809L',
                    '-Wall','-Wextra','-Werror','-I'+str(src),str(ROOT/'score_routes.c'),
                    *[str(src/p) for p in move_tools.SOURCES],'-lz','-lm','-o',str(staged)],check=True)
    if source_identity()!=identity:
        staged.unlink();raise ValueError('Sources changed during compilation')
    staged.replace(binary)
    move_tools.atomic_json(manifest,identity)
    return binary


def command(binary,args):
    return [str(binary),str(args.rom.resolve()),args.game,args.skill,
            format(args.start_delay,'.17g'),str(args.max_seconds),
            '--difficulty',str(getattr(args,'difficulty',0))]
