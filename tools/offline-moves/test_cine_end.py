#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A counterfactual copy and a death/footer lookalike cannot certify an end."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

import moves

ROOT=Path(__file__).resolve().parent


class EndObserverTest(unittest.TestCase):
    def test_end_requires_the_actual_replay_and_successful_rom_footer(self):
        program=r'''
#define main original_end_main
#include "cine_end_replay.c"
#undef main
#include <assert.h>
static uint8_t dummy(void *ctx,uint16_t address){(void)ctx;(void)address;return 0;}
static void setup(CineBoard *b) {
    memset(b,0,sizeof *b);b->cpu.pc=0x1235;b->cpu.iyh=0xa0;b->cpu.iyl=0xe0;
    b->ram[0xe0]=47;b->ram[0xe3]=0x34;b->ram[0xe4]=0x12;
}
int main(void) {
    CineBoard actual,counterfactual;setup(&actual);setup(&counterfactual);
    end_pc=0x1234;winning_frame[0]=winning_frame[1]=0x1234;
    completion_read=dummy;replay_board=&actual;observed_success=false;
    observe_end(&counterfactual,end_pc);assert(!observed_success);
    actual.ram[0xe3]=0x35;observe_end(&actual,end_pc);assert(!observed_success);
    actual.ram[0xe3]=0x34;actual.ram[0xe0]=63;
    observe_end(&actual,end_pc);assert(!observed_success);
    actual.ram[0xe0]=47;actual.cpu.pc=end_pc+2;
    observe_end(&actual,end_pc);assert(!observed_success);
    actual.cpu.pc=end_pc+1;observe_end(&actual,end_pc);assert(observed_success);
    return 0;
}
'''
        moves.verify_vendor();vendor=ROOT/'vendor/src'
        with tempfile.TemporaryDirectory(prefix='end-observer-',dir=ROOT.parents[1]/'local-tools') as temporary:
            folder=Path(temporary);source=folder/'test.c';source.write_text(program);binary=folder/'test'
            built=subprocess.run([os.environ.get('CC','cc'),'-O1','-std=c11','-D_POSIX_C_SOURCE=200809L',
                '-Wall','-Wextra','-Werror','-I'+str(ROOT),'-I'+str(vendor),str(source),
                *[str(vendor/p) for p in moves.SOURCES],'-lz','-lm','-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            checked=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(checked.returncode,0,checked.stderr)


if __name__=='__main__':unittest.main()
