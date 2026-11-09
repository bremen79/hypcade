#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build/run the offline ROM explorer, or compile its hint files for Hypseus."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import time
import zipfile
import zlib

ROOT = Path(__file__).resolve().parent
CHIPS = {
    'dle21': [('dle21_u1.bin', 0x4f8af481), ('dle21_u2.bin', 0x5fca04c5), ('dle21_u3.bin', 0xc14f36b3)],
    'ace': [('sa_a3_u1.bin', 0x427522d0), ('sa_a3_u2.bin', 0x18d0262d),
            ('sa_a3_u3.bin', 0x4646832d), ('sa_a3_u4.bin', 0x57db2a79), ('sa_a3_u5.bin', 0x85cbcdc4)],
}
SOURCES = ['games/cinematronics/board.c', 'cpu/z80.c', 'audio/ay8910.c',
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


def build(binary, cc='cc'):
    verify_vendor()
    src = ROOT / 'vendor/src'
    subprocess.run([cc, '-O3', '-std=c11', '-D_POSIX_C_SOURCE=200809L',
                    '-Wall', '-Wextra', '-I' + str(src), str(ROOT / 'extract.c'),
                    *[str(src / p) for p in SOURCES], '-lz', '-lm', '-o', str(binary)], check=True)


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as f:
        json.dump(data, f, indent=2)
        f.write('\n')
        temp = Path(f.name)
    os.replace(temp, path)


def extract(args):
    if not 1 <= args.nodes <= 4096 or not 1 <= args.sample_ticks <= 30:
        raise ValueError('--nodes must be 1..4096; --sample-ticks must be 1..30')
    if not 0 <= args.start_delay <= 60:
        raise ValueError('--start-delay must be 0..60 seconds')
    rom = args.rom.resolve()
    chips = identity(rom, args.game)
    if args.output.resolve() == rom:
        raise ValueError('Output must not overwrite the ROM')
    vendor = verify_vendor()
    with tempfile.TemporaryDirectory(prefix='hypseus-hints-') as tmp:
        binary = Path(tmp) / 'extract'
        build(binary, args.cc)
        started = time.perf_counter()
        result = subprocess.run([str(binary), str(rom), args.game, str(args.nodes),
                                 args.dsw1, args.dsw2, args.skill, str(args.sample_ticks), args.mode, str(args.start_delay)],
                                stdout=subprocess.PIPE, text=True, check=True)
        elapsed = time.perf_counter() - started
    records = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    config = next(r for r in records if r['type'] == 'config')
    summary = next(r for r in records if r['type'] == 'summary')
    trials = [r for r in records if r['type'] == 'trial']
    # Keep all evidence, including fatal/ignored/unresolved trials. Consumers must
    # not turn a timeout into an accepted move or merge conflicting observations.
    candidates = {}
    conflicts = set()
    for r in trials:
        key = (r['headers'], r['outcome'], r['control'], r['frame'])
        if r['verdict'] == 'continuation':
            candidates.setdefault(key, {k: r[k] for k in
                ['headers', 'outcome', 'control', 'frame', 'entry', 'window', 'remaining_ticks']})
        else:
            conflicts.add(key)
    hints = [candidates[k] for k in sorted(candidates) if k not in conflicts]
    doc = dict(schema=1, signature_schema=2, game=args.game, rom_chips=chips, engine_revision=vendor['revision'],
               signature_header_sha256=hashlib.sha256((ROOT/'../../android/app/jni/arcade_signature.h').read_bytes()).hexdigest(),
               engine_sha256=hashlib.sha256((ROOT/'extract.c').read_bytes()).hexdigest(),
               vendor_manifest_sha256=hashlib.sha256((ROOT/'vendor/provenance.json').read_bytes()).hexdigest(),
               configuration={**config, 'skill': args.skill, 'start_delay': args.start_delay},
               exploration=dict(mode=args.mode, node_budget=args.nodes if args.mode == "explore" else None, sample_ticks=args.sample_ticks,
                                sample_period_cycles=args.sample_ticks*131072,
                                cpu_hz=4000000, press_cycles=400000, wall_seconds=elapsed, **summary),
               evidence=('death-free campaign to ROM-driven victory playback' if summary['complete'] else
                         'bounded-two-decision-continuation; not a proof of game completion'),
               timing='tested press instants plus live ROM countdown; not exhaustive acceptance edges',
               hints=hints, trials=trials, no_input=[r for r in records if r['type'] == 'no_input'])
    atomic_json(args.output, doc)
    print(f'{args.game}: {len(hints)} hint samples, {len(trials)} trials; complete={summary['complete']} -> {args.output}')


def compile_hints(paths, output, baseline=None, require_complete=False):
    groups = {game: set() for game in CHIPS}
    canonical = {game: set() for game in CHIPS}
    canonical_blocked = {game: set() for game in CHIPS}
    blocked = {game: set() for game in CHIPS}
    if baseline is not None:
        text = baseline.read_text()
        for game in CHIPS:
            match = re.search(r'static const SafeOutcome '+game+r'_moves\[\] = \{(.*?)\};', text, re.S)
            if not match:
                raise ValueError('Invalid baseline: missing '+game)
            rows = re.findall(r'\{UINT64_C\(0x([0-9a-f]+)\), (\d+), (\d+)\}', match[1])
            if not rows: raise ValueError('Empty baseline: '+game)
            groups[game].update((int(h,16), int(o), int(f)) for h,o,f in rows)
    for path in paths:
        doc = json.loads(path.read_text())
        game = doc.get('game')
        if doc.get('schema') != 1 or game not in CHIPS:
            raise ValueError('Unsupported hint file: ' + str(path))
        if require_complete:
            report = doc.get('exploration', {})
            if (report.get('complete') is not True or report.get('late_inputs') != 0 or
                    report.get('lives_before', 0) <= 0 or
                    report.get('lives_before') != report.get('lives_after')):
                raise ValueError('Campaign did not finish without deaths/late inputs: '+str(path))
        expected = [(name, f'{crc:08x}') for name, crc in CHIPS[game]]
        if [(c['name'], c['crc32']) for c in doc['rom_chips']] != expected:
            raise ValueError('ROM identity mismatch in ' + str(path))
        signature = doc.get('signature_schema', 1)
        if signature not in (1,2): raise ValueError('Unknown signature schema')
        target = canonical if signature == 2 else groups
        rejected = canonical_blocked if signature == 2 else blocked
        for r in doc['trials']:
            if r['verdict'] != 'continuation':
                rejected[game].add((r['headers'], r['outcome'], r['frame']))
        for r in doc['hints']:
            key, outcome, frame = int(r['headers'], 16), r['outcome'], r['frame']
            if not (0 <= key < 2**64 and 0 <= outcome < 255 and 0 <= frame <= 100000):
                raise ValueError('Invalid hint record in ' + str(path))
            target[game].add((key, outcome, frame))
    lines = ['// SPDX-License-Identifier: GPL-3.0-or-later',
             '// Generated by tools/offline-hints/hints.py; see android/hints/campaigns/manifest.json.',
             '// No ROM bytes. Runtime obtains window timing from live ROM RAM.']
    if not any(groups.values()) and any(canonical.values()):
        # 0xff is never a valid hint outcome: keep an inert legacy array slot.
        for game in groups: groups[game].add((0,255,0))
    for tables, conflicts, suffix in [(groups, blocked, ''), (canonical, canonical_blocked, '_canonical')]:
        if not any(tables.values()):
            # Runtime consumes both schemas; absent schemas get inert slots.
            for game in tables: tables[game].add((0,255,0))
        for game, observations in tables.items():
            safe = [(h,o,f) for h,o,f in sorted(observations)
                    if not any(int(bh,16)==h and bo==o and abs(bf-f)<=24
                               for bh,bo,bf in conflicts[game])]
            if not safe:
                raise ValueError(f'No unconflicted hints for {game}{suffix}; supply both games, or explore more')
            lines.append(f'static const SafeOutcome {game}{suffix}_moves[] = {{')
            lines += [f'    {{UINT64_C(0x{h:016x}), {o}, {f}}},' for h,o,f in safe]
            lines.append('};')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Generate first, then replace: a failed compile never destroys existing APK tables.
    with tempfile.NamedTemporaryFile(mode='w', dir=output.parent, delete=False) as f:
        f.write('\n'.join(lines) + '\n')
        temp = Path(f.name)
    os.replace(temp, output)
    print('APK include written:', output)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    e = sub.add_parser('extract', help='run CPU/player offline and write one ROM hint JSON')
    e.add_argument('--game', choices=CHIPS, required=True)
    e.add_argument('--rom', type=Path, required=True)
    e.add_argument('--output', type=Path, required=True)
    e.add_argument('--mode', choices=['campaign', 'explore'], default='campaign')
    e.add_argument('--start-delay', type=float, default=0)
    e.add_argument('--nodes', type=int, default=128)
    e.add_argument('--sample-ticks', type=int, default=1)
    e.add_argument('--skill', choices=['cadet', 'captain', 'ace'], default='ace')
    def bank(s):
        if s == 'default': return s
        v = int(s, 16)
        if not 0 <= v <= 255: raise argparse.ArgumentTypeError('DIP bank must be 00..ff')
        return f'{v:02x}'
    e.add_argument('--dsw1', type=bank, default='default')
    e.add_argument('--dsw2', type=bank, default='default')
    e.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    c = sub.add_parser('compile', help='compile both ROM JSONs to the existing APK table format')
    c.add_argument('files', type=Path, nargs='+')
    c.add_argument('--output', type=Path, required=True)
    c.add_argument('--baseline', type=Path)
    c.add_argument('--require-complete', action='store_true')
    args = p.parse_args()
    try:
        if args.command == 'extract': extract(args)
        else: compile_hints(args.files, args.output, args.baseline, args.require_complete)
    except (ValueError, OSError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        p.exit(1, f'Error: {error}\n')


if __name__ == '__main__': main()
