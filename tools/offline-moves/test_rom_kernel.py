#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Original tiny Z80 programs checking the validator, not commercial ROMs."""
from pathlib import Path
import tempfile
import unittest

from rom_kernel import Kernel


def program(code):
    rom = bytearray(512)
    rom[0x100:0x100 + len(code)] = bytes(code)
    return bytes(rom)


class KernelTest(unittest.TestCase):
    def test_input_port_is_explicit_and_does_not_leak_between_calls(self):
        rom = program((0x3A, 8, 0xC0, 0x32, 0, 0xA0, 0xC9))
        with tempfile.TemporaryDirectory() as directory:
            kernel = Kernel(rom, Path(directory))
            for value in (255, 239, 254):
                ram, _ = kernel.call(bytes(1024), 0x100, input_port=value)
                self.assertEqual(ram[0], value)
            ram, _ = kernel.call(bytes(1024), 0x100)
            self.assertEqual(ram[0], 0)

    def test_refresh_observation_and_separate_rom_stores(self):
        # LD A,R; LD (A000),A; RET.
        refresh_rom = program((0xED, 0x5F, 0x32, 0, 0xA0, 0xC9))
        constant_rom = program((0x3E, 42, 0x32, 0, 0xA0, 0xC9))
        with tempfile.TemporaryDirectory() as directory:
            refresh = Kernel(refresh_rom, Path(directory))
            constant = Kernel(constant_rom, Path(directory))
            for seed in (0, 1, 126, 127, 128, 254, 255):
                ram, info = refresh.call(bytes(1024), 0x100, refresh=seed)
                expected = (seed & 128) | ((seed + 2) & 127)
                self.assertEqual(info['observations'], [(0x100, expected)])
                self.assertEqual(ram[0], expected)
                ram, info = constant.call(bytes(1024), 0x100)
                self.assertEqual(ram[0], 42)
                self.assertEqual(info['observations'], [])
            with self.assertRaisesRegex(ValueError, 'complete 1 KiB'):
                refresh.call(bytes(3), 0x100)


if __name__ == '__main__':
    unittest.main()
