#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Original-ROM no-input polling transfers, between interrupts.

Only a complete iteration with released controls, cleared edge latches, a
positive footer timer and no service/end flag is summarized. IRQ entry,
pressed/held inputs and the final footer exit remain separate transfers.
"""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import argparse
import ctypes as c
from dataclasses import dataclass
import hashlib
from itertools import product
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
NATIVE=r'''
#include "rom_kernel.c"
unsigned poll_once(uint8_t *ram,unsigned entry,unsigned iy,unsigned refresh,uint32_t *result) {
    memcpy(mem,rom,sizeof mem);memcpy(mem+0xa000,ram,1024);
    memset(accessed,0,sizeof accessed);memset(modified,0,sizeof modified);
    observation_count=0;input_port=255;
    z80_init(&cpu,(Z80Bus){0,rd,wr,in,out});cpu.pc=entry;cpu.sp=0xa3f0;cpu.r=refresh;
    cpu.iyh=iy>>8;cpu.iyl=iy;
    unsigned steps=0,m1=0,cycles=0;
    do {
        unsigned before=cpu.r;cycles+=(unsigned)z80_step(&cpu);
        m1+=(cpu.r-before)&127;++steps;
    }while(cpu.pc!=entry && steps<10000);
    result[0]=cpu.r;result[1]=cpu.pc;result[2]=steps;result[3]=m1;
    result[4]=cycles;result[5]=observation_count;
    memcpy(ram,mem+0xa000,1024);
    if(steps>=10000)return 0;
    /* A closed iteration normalizes the scratch registers. Check the exact
     * fixed point needed to skip additional identical released-input polls. */
    Z80 fixed=cpu;uint8_t saved[1024];memcpy(saved,mem+0xa000,sizeof saved);
    unsigned again_steps=0,again_m1=0,again_cycles=0;
    do {
        unsigned before=cpu.r;again_cycles+=(unsigned)z80_step(&cpu);
        again_m1+=(cpu.r-before)&127;++again_steps;
    }while(cpu.pc!=entry && again_steps<10000);
    cpu.r=fixed.r;
    if(again_steps!=steps || again_m1!=m1 || again_cycles!=cycles ||
            memcmp(&cpu,&fixed,sizeof cpu) || memcmp(saved,mem+0xa000,sizeof saved))return 0;
    return steps<10000;
}
'''


def locate(rom):
    found=[]
    for pc in range(len(rom)-16):
        if (rom[pc:pc+4]==bytes.fromhex('fdcb0546') and rom[pc+4]==0x20
                and rom[pc+6]==0xc3 and rom[pc+9:pc+13]==bytes.fromhex('fdcb0076')):
            found.append(pc)
        elif rom[pc:pc+7]==bytes.fromhex('fdcb007620e9c3'):
            found.append(pc)
    if not found or any(rom[pc:pc+32]!=rom[found[0]:found[0]+32] for pc in found):
        raise ValueError('Unknown or ambiguous original input-poll loop')
    return found[0]


class PollKernel:
    def __init__(self,rom,build):
        moves.verify_vendor();build.mkdir(parents=True,exist_ok=True)
        source=build/'poll-kernel.c';source.write_text(NATIVE)
        key=hashlib.sha256(rom+NATIVE.encode()+(source_path('rom_kernel.c')).read_bytes()).hexdigest()[:16]
        library=build/('poll-'+key+'.so');vendor=ROOT/'vendor/src'
        subprocess.run([os.environ.get('CC','cc'),'-O2','-std=c11','-shared','-fPIC','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT),'-I'+str(vendor),str(source),str(vendor/'cpu/z80.c'),'-o',str(library)],check=True)
        self.native=c.CDLL(str(library.resolve()))
        self.native.rom_init.argtypes=[c.POINTER(rom_kernel.Byte),c.c_uint]
        self.native.poll_once.argtypes=[c.POINTER(rom_kernel.Byte),c.c_uint,c.c_uint,c.c_uint,c.POINTER(c.c_uint32)]
        self.native.poll_once.restype=c.c_uint
        self.native.rom_access.argtypes=[c.POINTER(rom_kernel.Byte),c.POINTER(rom_kernel.Byte)]
        self.native.rom_init((rom_kernel.Byte*len(rom)).from_buffer_copy(rom),len(rom))

    def once(self,ram,entry,iy,seed=0):
        data=rom_kernel.RAM(*ram);result=(c.c_uint32*6)()
        if not self.native.poll_once(data,entry,iy,seed,result):raise ValueError('No-input polling iteration did not close')
        reads,writes=rom_kernel.RAM(),rom_kernel.RAM();self.native.rom_access(reads,writes)
        return bytes(data),tuple(result),{i for i,v in enumerate(reads) if v},{i for i,v in enumerate(writes) if v}


def memory(descriptors,footer=1,flags=7,effects=0):
    if len(descriptors)>16:raise ValueError('Too many descriptors')
    if type(footer) is not int or not 0<footer<=65535:raise ValueError('Expected a positive footer countdown')
    if any(type(v) is not int or not 0<=v<=255 for v in (flags,effects)):
        raise ValueError('Expected byte-sized footer flags/effects')
    if flags&0xc0 or effects&0x40:raise ValueError('Service/end flags are outside this transfer')
    ram=bytearray(1024)
    for i,(count,timers) in enumerate(descriptors):
        if type(count) is not int or count not in (1,2,3) or len(timers)!=4 or any(type(x) is not int or not 0<=x<=255 for x in timers):
            raise ValueError('Invalid descriptor timers/window count')
        if any(timers[count+1:]):raise ValueError('Nonzero nonexistent window')
        at=0xe0+16*i;ram[at]=0x84;ram[at+1]=count
        ram[at+12:at+16]=bytes(timers)
    at=0xe0+16*len(descriptors);ram[at]=flags;ram[at+5]=effects
    ram[at+14:at+16]=footer.to_bytes(2,'little')
    return ram,0xa000+at


@dataclass(frozen=True)
class PollCost:
    m1: int
    cycles: int

    def repeat(self,count):
        """Compose iterations only while timers/inputs stay unchanged."""
        if type(count) is not int or count<0:raise ValueError('Expected nonnegative iteration count')
        return PollCost(self.m1*count,self.cycles*count)

    def fit(self,budget):
        """Complete iterations fitting before the next external event.

        The residual instruction fragment still needs exact CPU execution.
        No IRQ, timer tick or physical input may occur inside this budget.
        """
        if type(budget) is not int or budget<0:raise ValueError('Expected a nonnegative cycle budget')
        count=budget//self.cycles
        return count,self.repeat(count),budget%self.cycles


def cost(game,descriptors,footer=1,flags=7,effects=0,cutoff=0):
    memory(descriptors,footer,flags,effects)  # Validate the transfer domain.
    if game not in rom_tables.LAYOUTS:raise ValueError('Unsupported ROM')
    if type(cutoff) is not int or not 0<=cutoff<=255:raise ValueError('Invalid A3 footer cutoff')
    if game=='ace' and footer==cutoff:raise ValueError('Footer has reached the ROM expiry cutoff')
    if game in ('ace','sae'):
        m1,cycles=(243,2031) if footer>=256 else ((247,2073) if game=='ace' else (248,2071))
    else:
        m1,cycles=(245,2051) if footer>=256 else (248,2080)
        if effects&1:m1+=6;cycles+=62
    for count,timers in descriptors:
        active=next((j for j,v in enumerate(timers) if v),None)
        if active==0:dm,dt=27,199
        elif active is None:dm,dt=28+9*count,211+52*count
        else:dm,dt=30+9*active,245+52*active
        m1+=dm;cycles+=dt
    return PollCost(m1,cycles)


def audit(rom,game,build):
    k=PollKernel(rom,build);entry=locate(rom)
    cases=0
    def verify(desc,footer=1,flags=7,effects=0,seed=0,mutator=None):
        nonlocal cases
        ram,iy=memory(desc,footer,flags,effects)
        if mutator:mutator(ram)
        before=bytearray(ram)
        after,result,reads,writes=k.once(ram,entry,iy,seed)
        if game not in ('ace','sae') and effects&1:before[10]&=254
        if after[:0x3d0]!=before[:0x3d0]:raise ValueError('Polling changed undeclared state')
        predicted=cost(game,desc,footer,flags,effects,cutoff=ram[0x16])
        if result[5] or result[3:5]!=(predicted.m1,predicted.cycles) or result[0]!=(seed+predicted.m1)&127:
            raise ValueError('Original polling refresh/cycles differ from literal path sum')
        allowed={0x40+j for j in range(12)}
        for i,(count,timers) in enumerate(desc):
            at=0xe0+16*i;active=next((j for j,v in enumerate(timers) if v),None)
            allowed.update((at,at+1))
            allowed.update(at+12+j for j in range(count+1 if active is None else active+1))
        at=iy-0xa000;allowed.update((at,at+15))
        if game not in ('ace','sae'):allowed.add(at+5)
        if footer<256:allowed.add(at+14)
        if game=='ace' and footer<256:allowed.add(0x16)
        if game not in ('ace','sae') and effects&1:allowed.add(10)
        if {a for a in reads if a<0x3d0}!=allowed:
            raise ValueError('Polling reads outside declared state: extra=%r missing=%r' %
                ({a for a in reads if a<0x3d0}-allowed,allowed-{a for a in reads if a<0x3d0}))
        if any(a<0x3d0 and a not in allowed for a in writes):raise ValueError('Undeclared polling write')
        cases+=1
    kinds=[]
    for count in (1,2,3):
        for active in range(count+2):
            timers=[0]*4
            if active<count+1:timers[active]=1
            kinds.append((count,timers))
            for value in range(1,256):
                row=list(timers)
                if active<count+1:
                    row[active]=value
                    for j in range(active+1,count+1):row[j]=173
                for seed in (0,127):verify([(count,row)],seed=seed)
    # Descriptor contributions compose in any order, including pointer-page
    # crossings. Exhaust type pairs and each slot in lists of all lengths.
    for left,right in product(kinds,repeat=2):verify([left,right],257, effects=1)
    for n in range(17):
        verify([(3,[0]*4)]*n)
        for i in range(n):
            for kind in kinds:
                desc=[(3,[0]*4)]*n;desc[i]=kind;verify(desc)
    for footer in (1,2,255,256,257,65535):
        for flags in range(64):
            for effects in (0,1,2,16,32,128,191):verify([(2,[0,0,17,0])],footer,flags,effects)
    # Header bits, direction, outcome mapping and stable low latch bits cannot
    # change a no-input branch. Enumerate their entire individual byte domains.
    for header in range(128,256):
        if (header&15)>10:continue
        for selector in range(64):
            def mutate(ram,header=header,selector=selector):
                ram[0xe0]=header;ram[0xe1]=3|(selector<<2)
                ram[0xe2:0xe6]=bytes((255,173,21,0));ram[0xe7]=255
                ram[10]=255
                for j in range(11):ram[0x40+j]=(selector+j)&31
            verify([(3,[0,0,17,19])],effects=1,mutator=mutate)
    if game=='ace':
        for cutoff in range(256):
            if cutoff!=35:
                verify([(2,[0,0,17,0])],35,mutator=lambda ram,cutoff=cutoff:ram.__setitem__(0x16,cutoff))
    return dict(game=game,rom_sha256=hashlib.sha256(rom).hexdigest(),entry_pc=entry,native_cases=cases,
                low_footer_base=cost(game,[]).__dict__,high_footer_base=cost(game,[],256).__dict__,
                descriptor_costs=dict(delay=[27,199],window0=[39,297],window1=[48,349],window2=[57,401],
                    exhausted='M1=28+9*windows; T-states=211+52*windows'),
                units=['M1 fetches','T-states'],
                repeated_transfer='Every native case also verifies identical second-pass T-states/M1, all scratch CPU fields except R, and the full RAM fixed point',
                limits='Inter-interrupt released-input iterations only; positive non-expired footer and cleared edge latches; IRQ, service, accepted input and footer exit are separate')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--roms',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    started=time.monotonic();rows=[]
    for game in rom_tables.LAYOUTS:
        row=audit(rom_tables.load(a.roms/(game+'.zip'),game),game,a.output/'build');rows.append(row)
        print(game,row['native_cases'],'poll transfers',flush=True)
    report=dict(cases=rows,native_cases=sum(r['native_cases'] for r in rows),seconds=time.monotonic()-started,
                peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                sources={n:hashlib.sha256((source_path(n)).read_bytes()).hexdigest() for n in
                         ('rom_poll_rules.py','rom_kernel.py','rom_kernel.c','rom_tables.py')})
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
