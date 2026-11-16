#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""ROM-derived accepted-input wait rules and exact loop refresh increments.

Contracts are between interrupts: the IRQ and later loader remain explicit
composition steps. No physical phase reachability is inferred from a loop alone.
"""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import argparse
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import time

import moves
import rom_kernel
import rom_tables

ROOT = CORE
SIGNATURE=bytes.fromhex('3e00ddbe0c20f9ddbe0d20f4ddbe0e20efddbe0f20ea')
NATIVE=r'''
#include "rom_kernel.c"
unsigned wait_once(uint8_t *ram,unsigned entry,unsigned ix,unsigned refresh,uint16_t *result) {
    memcpy(mem,rom,sizeof mem);memcpy(mem+0xa000,ram,1024);
    memset(accessed,0,sizeof accessed);memset(modified,0,sizeof modified);
    z80_init(&cpu,(Z80Bus){0,rd,wr,in,out});cpu.pc=entry;cpu.r=refresh;
    cpu.ixh=ix>>8;cpu.ixl=ix;
    unsigned steps=0;
    do {z80_step(&cpu);++steps;}while(cpu.pc!=entry && cpu.pc!=entry+22 && steps<32);
    result[0]=cpu.r;result[1]=cpu.pc;result[2]=steps;
    memcpy(ram,mem+0xa000,1024);
    return steps<32;
}
'''


def waits_for_descriptor(entry,window):
    """261A–264C (US D): accepted outcome pointer selects an extra-byte bit."""
    if not entry['header']&16:return False
    if entry['extra'] is None:raise ValueError('Flagged input has no extra byte')
    index=(entry['selector']>>(2+2*window))&3
    bit=7 if index==0 else 6 if index==1 else 5
    return bool(entry['extra']&(1<<bit))


def iteration_m1(first_nonzero):
    """One LD plus three M1 fetches per visited indexed compare/branch pair."""
    if first_nonzero is None:return 13
    if type(first_nonzero) is not int or not 0<=first_nonzero<4:
        raise ValueError('Expected delay/window byte index 0..3')
    return 1+3*(first_nonzero+1)


def windows(record):
    result=[]
    for entry in record['inputs']:
        for window in entry['windows']:
            if window['outcome']==255 or not window['ticks']:continue
            wait=waits_for_descriptor(entry,window['window'])
            active=window['window']+1
            result.append(dict(slot=entry['slot'],window=window['window'],control=entry['control'],
                outcome=window['outcome'],wait_until_descriptor_exhausted=wait,
                active_loop_m1=iteration_m1(active) if wait else None,
                active_loop_parity=iteration_m1(active)&1 if wait else None,
                following_window_ticks=[w['ticks'] for w in entry['windows'][window['window']+1:]],
                timing_proof_scope='Inter-interrupt loop only; later windows/IRQ are separate'))
    return result


class WaitKernel:
    def __init__(self,rom,build):
        moves.verify_vendor();build.mkdir(parents=True,exist_ok=True)
        source=build/'wait-kernel.c';source.write_text(NATIVE)
        key=hashlib.sha256(rom+NATIVE.encode()+(source_path('rom_kernel.c')).read_bytes()).hexdigest()[:16]
        library=build/('wait-'+key+'.so');vendor=ROOT/'vendor/src'
        subprocess.run([os.environ.get('CC','cc'),'-O2','-std=c11','-shared','-fPIC','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT),'-I'+str(vendor),str(source),str(vendor/'cpu/z80.c'),'-o',str(library)],check=True)
        self.native=c.CDLL(str(library.resolve()))
        self.native.rom_init.argtypes=[c.POINTER(rom_kernel.Byte),c.c_uint]
        self.native.wait_once.argtypes=[c.POINTER(rom_kernel.Byte),c.c_uint,c.c_uint,c.c_uint,c.POINTER(c.c_uint16)]
        self.native.wait_once.restype=c.c_uint
        self.native.rom_access.argtypes=[c.POINTER(rom_kernel.Byte),c.POINTER(rom_kernel.Byte)]
        self.native.rom_call.argtypes=[c.POINTER(rom_kernel.Byte)]+[c.c_uint]*8+[c.POINTER(c.c_uint16)]
        self.native.rom_call.restype=c.c_uint
        self.native.rom_init((rom_kernel.Byte*len(rom)).from_buffer_copy(rom),len(rom))

    def once(self,ram,entry,seed):
        data=rom_kernel.RAM(*ram);result=(c.c_uint16*3)()
        if not self.native.wait_once(data,entry,0xa0e0,seed,result):raise ValueError('Wait-loop iteration did not close')
        reads,writes=rom_kernel.RAM(),rom_kernel.RAM();self.native.rom_access(reads,writes)
        return bytes(data),tuple(result),{i for i,v in enumerate(reads) if v},{i for i,v in enumerate(writes) if v}

    def gate(self,ram,pc,stop):
        data=rom_kernel.RAM(*ram);result=(c.c_uint16*6)()
        if not self.native.rom_call(data,pc,stop,0xa030,0,0,0xa200,0xa0e0,0,result):
            raise ValueError('Accepted-input wait gate did not reach its boundary')
        reads,writes=rom_kernel.RAM(),rom_kernel.RAM();self.native.rom_access(reads,writes)
        return bytes(data),{i for i,v in enumerate(reads) if v}


def audit(rom,game,build):
    entry=rom.find(SIGNATURE)
    if entry<0:raise ValueError('Unrecognized accepted-input wait loop: '+game)
    kernel=WaitKernel(rom,build)
    cases=0
    for active in range(4):
        for value in range(1,256):
            ram=bytearray(1024)
            ram[0xec+active]=value
            # Later nonzero bytes cannot affect this iteration; assert its
            # exact read-set rather than enumerate an irrelevant 256^suffix.
            for following in range(active+1,4):ram[0xec+following]=173
            for seed in (0,7,127):
                actual,(r,pc,steps),reads,writes=kernel.once(ram,entry,seed)
                if r != ((seed+iteration_m1(active))&127) or pc!=entry or steps!=3+2*active:
                    raise ValueError('Original wait-loop increment/path differs from rule')
                if reads!={0xec+i for i in range(active+1)} or writes or actual!=ram:
                    raise ValueError('Wait iteration reads/writes more than its timer prefix')
                cases+=1
    for seed in (0,7,127):
        ram=bytearray(1024);actual,(r,pc,steps),reads,writes=kernel.once(ram,entry,seed)
        if r!=((seed+13)&127) or pc!=entry+22 or steps!=9 or writes or reads!=set(range(0xec,0xf0)):
            raise ValueError('All-zero wait exit differs from rule')
        cases+=1
    gate=rom.rfind(bytes.fromhex('ddcb0066'),0,entry)
    if gate<0:
        raise ValueError('Unknown accepted-input descriptor gate')
    if rom[gate+6]==0x2a:
        pointer_cell=rom_tables.word(rom,gate+7)
    elif rom[gate+6]==0xc3:
        # SAE restores scoring before rejoining the original wait gate.
        patch=rom_tables.word(rom,gate+7)
        if rom[patch:patch+6]!=bytes.fromhex('210aa0cb8e2a'):
            raise ValueError('Unknown patched accepted-input gate')
        pointer_cell=rom_tables.word(rom,patch+6)
    else:raise ValueError('Unknown accepted-input pointer load')
    gate_cases=0
    for flagged in (False,True):
        for index in range(4):
            for extra in range(256):
                ram=bytearray(1024)
                header=0xf4 if flagged else 0xe4
                ram[0xe0]=header;ram[0xe7]=extra
                at=pointer_cell-0xa000
                ram[at:at+2]=(0xa0e2+index).to_bytes(2,'little')
                actual,reads=kernel.gate(ram,gate,entry+22)
                expected=waits_for_descriptor(dict(header=header,extra=extra,selector=1|(index<<2)),0)
                if bool(actual[8]&2)!=expected or bool(set(range(0xec,0xf0))&reads)!=expected:
                    raise ValueError('Original accepted-input gate differs from the outcome/extra-bit rule')
                gate_cases+=1
    inventory=rom_tables.inventory(rom,game)
    rows=[dict(address=r['address'],windows=windows(r)) for r in inventory['records'] if r['inputs']]
    return dict(game=game,rom_sha256=hashlib.sha256(rom).hexdigest(),wait_pc=entry,gate_pc=gate,
                native_cases=cases+gate_cases,wait_cases=cases,gate_cases=gate_cases,
                instruction_path_signature_sha256=hashlib.sha256(SIGNATURE).hexdigest(),records=rows,
                lemma='While the third timer byte alone is active, every uninterrupted polling iteration adds 10 to R and preserves parity; the all-zero exit adds 13',
                limits='This lemma alone excludes neither IRQ-dependent phase changes nor later-window loops; not a whole-game timing proof')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--roms',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);started=time.monotonic();rows=[]
    for game in rom_tables.LAYOUTS:
        row=audit(rom_tables.load(a.roms/(game+'.zip'),game),game,a.output/'build')
        rows.append(row);print(game,row['native_cases'],'wait-loop cases',hex(row['wait_pc']),flush=True)
    report=dict(cases=rows,native_cases=sum(r['native_cases'] for r in rows),
                seconds=time.monotonic()-started,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                sources={n:hashlib.sha256((source_path(n)).read_bytes()).hexdigest() for n in
                         ('rom_wait_rules.py','rom_kernel.py','rom_kernel.c','rom_tables.py')},
                z80_sha256=hashlib.sha256((source_path('vendor/src/cpu/z80.c')).read_bytes()).hexdigest())
    (a.output/'report.json').write_text(json.dumps(report,separators=(',',':'))+'\n')


if __name__=='__main__':main()
