#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sequential finite-domain audits of short routines using the original Z80."""
import ctypes
import hashlib
import os
from pathlib import Path
import subprocess

import moves

ROOT = Path(__file__).resolve().parent
Byte = ctypes.c_uint8
RAM = Byte * 1024


class Kernel:
    def __init__(self, rom, build):
        if not 0 < len(rom) <= 65536:
            raise ValueError('ROM must fit the 16-bit address space')
        moves.verify_vendor()
        build = Path(build).resolve()
        build.mkdir(parents=True, exist_ok=True)
        # Separate native global stores when auditing different ROMs in one
        # Python process. dlopen caches handles by path.
        library = build / ('rom-kernel-' + hashlib.sha256(rom).hexdigest()[:16] + '.so')
        src = ROOT / 'vendor/src'
        subprocess.run([os.environ.get('CC', 'cc'), '-O2', '-std=c11', '-fPIC', '-shared',
                        '-Wall', '-Wextra', '-Werror', '-I' + str(src), str(ROOT / 'rom_kernel.c'),
                        str(src / 'cpu/z80.c'), '-o', str(library)], check=True)
        self.native = ctypes.CDLL(str(library))
        self.native.rom_init.argtypes = [ctypes.POINTER(Byte), ctypes.c_uint]
        self.native.rom_call.argtypes = [ctypes.POINTER(Byte)] + [ctypes.c_uint] * 8 + [ctypes.POINTER(ctypes.c_uint16)]
        self.native.rom_call.restype = ctypes.c_uint
        self.native.rom_inputs.argtypes = [ctypes.c_uint]
        self.native.rom_access.argtypes = [ctypes.POINTER(Byte), ctypes.POINTER(Byte)]
        self.native.rom_observations.argtypes = [ctypes.POINTER(ctypes.c_uint16)]
        self.native.rom_observations.restype = ctypes.c_uint
        self.native.rom_init((Byte * len(rom)).from_buffer_copy(rom), len(rom))

    def call(self, ram, pc, *, stop=0xdead, de=0xa030, hl=0, bc=0, iy=0xa200, ix=0, refresh=0, input_port=None):
        if len(ram) != 1024:
            raise ValueError('Expected the complete 1 KiB board RAM')
        if input_port is not None and (type(input_port) is not int or not 0 <= input_port <= 255):
            raise ValueError('Input port must be an unsigned byte')
        self.native.rom_inputs(256 if input_port is None else input_port)
        data, result = RAM(*ram), (ctypes.c_uint16 * 6)()
        n = self.native.rom_call(data, pc, stop, de, hl, bc, iy, ix, refresh, result)
        if not n:
            raise ValueError('ROM routine did not reach %04x from %04x (at %04x)' % (stop, pc, result[5]))
        observations = (ctypes.c_uint16 * 128)()
        count = self.native.rom_observations(observations)
        if count > 64:
            raise ValueError('ROM observation budget exceeded')
        return bytearray(data), dict(bc=result[0], hl=result[1], de=result[2], refresh=result[3],
                                    a=result[4], instructions=n,
                                    observations=[(observations[2*i], observations[2*i+1]) for i in range(count)])

    def access(self):
        reads, writes = RAM(), RAM()
        self.native.rom_access(reads, writes)
        return ({i for i, v in enumerate(reads) if v}, {i for i, v in enumerate(writes) if v})
