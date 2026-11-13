#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""No commercial files required. Optional real-ROM runs are documented separately."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('moves', Path(__file__).with_name('moves.py'))
move_tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(move_tools)


class OfflineMovesTest(unittest.TestCase):
    def test_vendor_manifest(self):
        move_tools.verify_vendor()

    def test_rom_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'game.zip'
            with zipfile.ZipFile(p, 'w') as z:
                for name, _ in move_tools.CHIPS['dle21']:
                    z.writestr(name.upper(), bytes(8192))
            # Uppercase filenames are accepted structurally; the wrong bytes fail CRC.
            with self.assertRaisesRegex(ValueError, 'checksum'):
                move_tools.identity(p, 'dle21')

    def test_snapshot_isolation_and_live_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'snapshot.c'
            source.write_text('''#define main extractor_main
#include "simulation.c"
#undef main
#include <assert.h>
int main(void) {
    Machine original = {0}, clone = {0};
    original.board.game = CINE_DRAGONS_LAIR;
    original.ldp.state = LDP_PLAYING;
    original.ldp.frame = 31080;
    assert(!offline_won(&original.board, &original.ldp)); /* no active life */
    original.board.digits[6] = 5;
    assert(offline_won(&original.board, &original.ldp));
    original.ldp.state = LDP_SEARCHING;
    assert(!offline_won(&original.board, &original.ldp));
    original.ldp.state = LDP_PLAYING;
    original.ldp.frame = 30740;
    assert(!offline_won(&original.board, &original.ldp)); /* last input is not victory */
    original.board.game = CINE_SPACE_ACE;
    original.ldp.frame = 32840;
    assert(offline_won(&original.board, &original.ldp));
    original.ldp.frame = 1148;
    assert(!offline_won(&original.board, &original.ldp)); /* attract */
    original.player.ldp = &original.ldp;
    original.board.cpu.bus.ctx = &original.board;
    original.board.laserdisc = cine_ldv1000_link(&original.player);
    original.board.ram[0xe0] = 0x84; /* left */
    original.board.ram[0xe1] = 1;
    original.board.ram[0xe2] = 7;
    original.board.ram[0xed] = 4;
    clone = original; connect_machine(&clone);
    assert(clone.player.ldp == &clone.ldp);
    assert(clone.board.cpu.bus.ctx == &clone.board);
    assert(clone.board.laserdisc.ctx == &clone.player);
    assert(original.player.ldp == &original.ldp);
    CineMove moves[16] = {{0}};
    assert(cine_open_moves(&clone.board, moves, 16) == 1);
    assert(moves[0].input == 4 && moves[0].outcome == 7);
    uint64_t h = headers_hash(&clone.board);
    clone.board.ram[0xec] = 2;
    assert(cine_open_moves(&clone.board, moves, 16) == 0);
    assert(headers_hash(&clone.board) == h); /* ticking does not change scene key */
    assert(original.board.ram[0xec] == 0);
    return 0;
}
''')
            src = move_tools.ROOT/'vendor/src'
            subprocess.run(['cc', '-O2', '-std=c11', '-D_POSIX_C_SOURCE=200809L',
                            '-I'+str(move_tools.ROOT), '-I'+str(src), str(source),
                            *[str(src/p) for p in move_tools.SOURCES], '-lz', '-lm', '-o', str(root/'test')], check=True)
            subprocess.run([str(root/'test')], check=True)


if __name__ == '__main__': unittest.main()
