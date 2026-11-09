#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""No commercial files required. Optional real-ROM runs are documented separately."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('hints', Path(__file__).with_name('hints.py'))
hints = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hints)


class OfflineHintsTest(unittest.TestCase):
    def test_vendor_manifest(self):
        hints.verify_vendor()

    def test_rom_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'game.zip'
            with zipfile.ZipFile(p, 'w') as z:
                for name, _ in hints.CHIPS['dle21']:
                    z.writestr(name.upper(), bytes(8192))
            # Uppercase filenames are accepted structurally; the wrong bytes fail CRC.
            with self.assertRaisesRegex(ValueError, 'checksum'):
                hints.identity(p, 'dle21')

    def test_compile_conflicts_and_atomic_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = []
            for game in hints.CHIPS:
                good = dict(headers='0123456789abcdef', outcome=3, frame=100,
                            control=1, verdict='continuation')
                bad = dict(good, frame=120, verdict='death')
                separate = dict(good, frame=200)
                doc = dict(schema=1, game=game,
                           rom_chips=[dict(name=n, crc32=f'{crc:08x}') for n, crc in hints.CHIPS[game]],
                           hints=[good, separate], trials=[good, bad, separate])
                p = root/(game+'.json'); p.write_text(json.dumps(doc)); paths.append(p)
            out = root/'moves.inc'
            hints.compile_hints(paths, out)
            text = out.read_text()
            self.assertNotIn(', 3, 100}', text)  # +/-24-frame runtime overlap with death
            self.assertEqual(text.count(', 3, 200}'), 2)
            with self.assertRaisesRegex(ValueError, 'Campaign did not finish'):
                hints.compile_hints(paths, out, require_complete=True)
            for path in paths:
                complete = json.loads(path.read_text())
                complete['exploration'] = dict(complete=True, lives_before=5, lives_after=5, late_inputs=0)
                path.write_text(json.dumps(complete))
            hints.compile_hints(paths, out, require_complete=True)
            failed = json.loads(paths[0].read_text())
            failed['exploration']['lives_after'] = 4
            paths[0].write_text(json.dumps(failed))
            with self.assertRaisesRegex(ValueError, 'Campaign did not finish'):
                hints.compile_hints(paths, out, require_complete=True)
            self.assertEqual(out.read_text(), text)
            # Verify the output really is consumed by the production C++ table type.
            test = root/'check.cpp'
            test.write_text('#include <cstdint>\nstruct SafeOutcome { uint64_t headers; uint8_t outcome; unsigned frame; };\n'
                            '#include "moves.inc"\nint main(){return dle21_moves[0].frame != 200 || ace_moves[0].frame != 200;}\n')
            subprocess.run(['c++', '-std=c++11', str(test), '-o', str(root/'check')], check=True)
            subprocess.run([str(root/'check')], check=True)
            with self.assertRaisesRegex(ValueError, 'No unconflicted hints'):
                hints.compile_hints(paths[:1], out)
            self.assertEqual(out.read_text(), text)
            doc = json.loads(paths[0].read_text());doc['rom_chips'][0]['crc32'] = '00000000'
            paths[0].write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                hints.compile_hints(paths, out)
            self.assertEqual(out.read_text(), text)

    def test_canonical_schema_without_legacy_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = []
            for game in hints.CHIPS:
                row = dict(headers='0123456789abcdef', outcome=3, frame=100,
                           control=1, verdict='continuation')
                doc = dict(schema=1, signature_schema=2, game=game,
                           rom_chips=[dict(name=n, crc32=f'{crc:08x}') for n, crc in hints.CHIPS[game]],
                           hints=[row], trials=[row])
                path = root/(game+'.json'); path.write_text(json.dumps(doc)); paths.append(path)
            out = root/'moves.inc'
            hints.compile_hints(paths, out)
            text = out.read_text()
            for game in hints.CHIPS:
                self.assertIn(game+'_canonical_moves[]', text)
                self.assertIn(game+'_moves[]', text)
            self.assertEqual(text.count(', 255, 0}'), 2)
            doc['signature_schema'] = 99
            paths[-1].write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError, 'Unknown signature'):
                hints.compile_hints(paths, out)
            self.assertEqual(text, out.read_text())

    def test_snapshot_isolation_and_live_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'snapshot.c'
            source.write_text('''#define main extractor_main
#include "extract.c"
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
            src = hints.ROOT/'vendor/src'
            subprocess.run(['cc', '-O2', '-std=c11', '-D_POSIX_C_SOURCE=200809L',
                            '-I'+str(hints.ROOT), '-I'+str(src), str(source),
                            *[str(src/p) for p in hints.SOURCES], '-lz', '-lm', '-o', str(root/'test')], check=True)
            subprocess.run([str(root/'test')], check=True)


if __name__ == '__main__': unittest.main()
