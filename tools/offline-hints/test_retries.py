#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Replay real ROM deaths offline and check the shipped native hint decoder.
Requires user-owned dle21.zip / ace.zip. Does not write ROM/RAM into the repo.
"""
import argparse
import ctypes
import json
from pathlib import Path
import subprocess
import tempfile
import hints


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--roms', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    hints.verify_vendor()
    identities = {game: hints.identity(args.roms/(game+'.zip'), game) for game in hints.CHIPS}
    repo = hints.ROOT.parents[1]
    results = []
    with tempfile.TemporaryDirectory(prefix='hypseus-retry-') as directory:
        tmp = Path(directory)
        src = hints.ROOT/'vendor/src'
        subprocess.run(['cc', '-O3', '-std=c11', '-D_POSIX_C_SOURCE=200809L',
                        '-I'+str(src), str(hints.ROOT/'retry_probe.c'),
                        *[str(src/p) for p in hints.SOURCES], '-lz', '-lm', '-o', str(tmp/'probe')], check=True)
        (tmp/'bridge.cpp').write_text('''#include "arcade_guidance.h"
#include <cstring>
extern "C" unsigned decode(const unsigned char *ram, unsigned frame, bool ace) {
 unsigned char memory[0xa800]={}; std::memcpy(memory+0xa000,ram,2048);
 auto r=arcade_decode_cine(memory,sizeof memory,ace,frame);
 return r.controls | (r.ready?256:0);
}
''')
        subprocess.run(['c++', '-shared', '-fPIC', '-O2', '-std=c++11', '-DHYPSEUS_GUIDANCE_HOST_TEST',
                        '-I'+str(repo/'android/app/jni'), str(tmp/'bridge.cpp'),
                        str(repo/'android/app/jni/arcade_guidance.cpp'), '-o', str(tmp/'decoder.so')], check=True)
        decoder = ctypes.CDLL(str(tmp/'decoder.so')).decode
        decoder.argtypes = [ctypes.c_char_p, ctypes.c_uint, ctypes.c_bool]
        decoder.restype = ctypes.c_uint
        for game in hints.CHIPS:
            for position in (1, 5, 20):
                replay = subprocess.run([str(tmp/'probe'), str(args.roms/(game+'.zip')), game,
                                         str(position), '2'], check=True, capture_output=True, text=True, timeout=180)
                deaths = checked = 0
                for line in replay.stdout.splitlines():
                    if line.startswith('DEATH '):
                        deaths += 1
                    elif line.startswith('SNAP ') and deaths:
                        _, index, lives, frame, action, ram = line.split()
                        result = decoder(bytes.fromhex(ram), int(frame), game == 'ace')
                        # The oracle can choose a different valid input when several
                        # are accepted. Require a live, known window after each retry.
                        assert result & 31 and result & 256, (game, position, deaths, index, frame, result)
                        checked += 1
                assert deaths == 2 and checked >= 41, (game, position, deaths, checked)
                results.append(dict(game=game, miss_after_moves=position, deaths=deaths, post_death_moves=checked))
                print(f'{game}: missed after {position} moves; {deaths} deaths; {checked} post-death hints passed', flush=True)
    assert identities == {game: hints.identity(args.roms/(game+'.zip'), game) for game in hints.CHIPS}
    if args.report:
        hints.atomic_json(args.report, dict(scope='real-ROM offline retries with production decoder; no video/UI/audio test', cases=results))

if __name__ == '__main__':
    main()
