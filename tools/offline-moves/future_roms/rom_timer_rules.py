#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact compact IRQ timer transfer and refresh potential from original ROMs.

Only the timer-update block is summarized. Sound, credits, IRQ entry/exit and
main-thread polling remain separate; this is not a whole-game phase proof.
"""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import argparse
from dataclasses import asdict,dataclass
import hashlib
from itertools import product
import json
from pathlib import Path
import resource
import time

import rom_kernel
import rom_tables

ROOT = CORE


def locate(rom):
    candidates=[]
    for i in range(len(rom)-64):
        if (rom[i:i+4]==bytes.fromhex('01e0a0cd') and rom[i+6:i+9]==bytes.fromhex('cb7e28')
                and rom[i+10:i+14]==bytes.fromhex('3e0c856f')):
            footer=i+10+rom[i+9]
            if (rom[footer:footer+8]==bytes.fromhex('fde5e13e0e856fcd') and
                    rom[footer+10:footer+17]==bytes.fromhex('30053600233600')):
                candidates.append((i,footer+17))
    if not candidates:raise ValueError('Unknown original IRQ timer block')
    return candidates[0]


def validate_block(rom,bounds):
    """Check every opcode in the timer loop and its straight-line helpers.

    The only value classes are zero/nonzero timer bytes and carry from a
    sixteen-bit subtraction of one. There is no value-specific positive
    footer branch to miss between the native boundary cases.
    """
    entry,stop=bounds;footer=stop-17
    body=bytearray(rom[entry:entry+50])
    targets={at:rom_tables.word(rom,entry+at) for at in (4,21,28,46)}
    for at in (4,21,28,46):body[at:at+2]=b'\0\0'
    body[9]=0
    expected=bytes.fromhex('01e0a0cd0000cb7e28003e0c856f3e00be280d35cd000001100009cd000018e6233e0fa528073e00be20e818f3cd000018d4')
    if body!=expected:raise ValueError('Timer loop instruction/branch structure changed')
    if targets[4]!=targets[21] or targets[28]!=targets[46]:raise ValueError('Inconsistent timer cursor helpers')
    if rom[targets[4]:targets[4]+3]!=bytes.fromhex('c5e1c9') or rom[targets[28]:targets[28]+3]!=bytes.fromhex('e5c1c9'):
        raise ValueError('Unknown timer cursor register-copy helper')
    gap=rom[entry+50:footer]
    if gap and not(len(gap)==4 and gap[:3]==bytes.fromhex('cbae18')):
        raise ValueError('Unknown code between timer loop and footer')
    dec=rom_tables.word(rom,footer+8);code=bytearray(rom[dec:dec+25])
    helpers={at:rom_tables.word(rom,dec+at) for at in (4,7,16,19)}
    for at in helpers:code[at:at+2]=b'\0\0'
    if code!=bytes.fromhex('4e2346cd0000cd0000010100a7ed42cd0000cd0000702b71c9'):
        raise ValueError('Unknown footer subtraction routine')
    for at,pattern in ((4,'e5d1c9'),(7,'c5e1c9'),(16,'e5c1c9'),(19,'d5e1c9')):
        pc=helpers[at]
        if rom[pc:pc+3]!=bytes.fromhex(pattern):raise ValueError('Footer arithmetic helper changed')


def checked(timers,footer):
    if len(timers)>16 or any(len(row)!=4 or any(type(v) is not int or not 0<=v<=255 for v in row) for row in timers):
        raise ValueError('Expected at most sixteen four-byte delay/window timers')
    if type(footer) is not int or not 0<=footer<=65535:raise ValueError('Invalid footer countdown')


def advance(timers,footer,ticks):
    checked(timers,footer)
    if type(ticks) is not int or ticks<0:raise ValueError('Ticks must be a nonnegative integer')
    result=[]
    for row in timers:
        remaining=ticks;updated=[]
        for value in row:
            used=min(value,remaining);updated.append(value-used);remaining-=used
        result.append(updated)
    return result,max(footer-ticks,0)


@dataclass(frozen=True)
class TimerRule:
    base: int
    empty_descriptor: int
    active: tuple
    positive_footer: int

    def __post_init__(self):
        if len(self.active)!=4 or any(type(v) is not int for v in (self.base,self.empty_descriptor,self.positive_footer,*self.active)):
            raise ValueError('Timer rule requires four integer byte coefficients')

    def potential(self,timers):
        checked(timers,0)
        return sum(a*v for row in timers for a,v in zip(self.active,row))%128

    def delta(self,timers,footer,ticks=1):
        after,last=advance(timers,footer,ticks)
        value=(ticks*(self.base+len(timers)*self.empty_descriptor)+self.potential(timers)
               -self.potential(after)+self.positive_footer*min(ticks,footer))%128
        return after,last,value


def memory(timers,footer):
    checked(timers,footer);ram=bytearray(1024)
    for i,row in enumerate(timers):
        at=0xe0+16*i;ram[at]=0x84;ram[at+12:at+16]=bytes(row)
    at=0xe0+16*len(timers);ram[at]=47;ram[at+14:at+16]=footer.to_bytes(2,'little')
    return ram,0xa000+at


def native(kernel,bounds,timers,footer,seed=0):
    ram,iy=memory(timers,footer)
    actual,regs=kernel.call(ram,bounds[0],stop=bounds[1],iy=iy,refresh=seed)
    expected,last=advance(timers,footer,1)
    predicted,_=memory(expected,last)
    if actual[:0x3d0]!=predicted[:0x3d0]:raise ValueError('Original timer block mutates more than the declared countdowns')
    reads,writes=kernel.access()
    allowed={0xe0+16*i for i in range(len(timers)+1)}
    for i,row in enumerate(timers):
        active=next((j for j,v in enumerate(row) if v),None)
        allowed.update(0xec+16*i+j for j in range(4 if active is None else active+1))
    allowed.update((iy-0xa000+14,iy-0xa000+15))
    if {i for i in reads if i<0x3d0}!=allowed:
        raise ValueError('Timer block reads undeclared state')
    if any(i<0x3d0 and i not in allowed for i in writes):raise ValueError('Timer block writes undeclared state')
    if regs['observations']:raise ValueError('Timer block unexpectedly reads R')
    return (regs['refresh']-seed)%128,expected,last


def audit(rom,game,build):
    kernel=rom_kernel.Kernel(rom,build);bounds=locate(rom);validate_block(rom,bounds);cases=0
    def sample(timers,footer,seed=0):
        nonlocal cases
        delta,_,_=native(kernel,bounds,timers,footer,seed);cases+=1;return delta
    base=sample([],0);empty=(sample([[0]*4],0)-base)%128
    coefficients=[]
    for active in range(4):
        row=[0]*4;row[active]=1
        coefficients.append((sample([row],0)-base-empty)%128)
    positive=(sample([],1)-base)%128
    # Literal path counts: base 46; empty descriptor 42; first-active paths
    # 21/28/36/44; a positive footer skips three clamp-to-zero instructions.
    rule=TimerRule(46,42,(-21,-14,-6,2),-3)
    if (base,empty,tuple(coefficients),positive)!=(46,42,(107,114,122,2),125):
        raise ValueError('Native calibration differs from literal instruction counts')
    def verify(timers,footer,seed=0):
        expected,last,delta=rule.delta(timers,footer)
        actual,rows,tail=native(kernel,bounds,timers,footer,seed)
        nonlocal cases
        cases+=1
        if (actual,rows,tail)!=(delta,expected,last):raise ValueError('Original timer refresh transfer differs from additive rule')
    # All values of a first-active byte, including 1->0; suffix bytes must
    # not affect this step. R itself is never inspected by the block.
    for active in range(4):
        for value in range(1,256):
            row=[0]*4;row[active]=value
            for j in range(active+1,4):row[j]=173
            for seed in (0,7,127,255):verify([row],0,seed)
    for count in range(17):
        for footer in (0,1,255,256,257,65535):verify([[0]*4 for _ in range(count)],footer)
        for slot in range(count):
            for active in range(4):
                rows=[[0]*4 for _ in range(count)];rows[slot][active]=1
                verify(rows,1)
    # Exhaust three independently active/inactive descriptors. Longer lists
    # are additionally exercised across the A0xx/A1xx pointer boundary.
    for pattern in product(range(5),repeat=3):
        rows=[]
        for active in pattern:
            row=[0]*4
            if active<4:row[active]=17
            rows.append(row)
        for footer in (0,257):verify(rows,footer,127)
    bulk_cases=0
    for ticks in (0,1,2,17,42,255):
        rows=[[1,2,3,4],[0,0,5,7],[2,0,0,0]];footer=19;delta=0
        start=[r[:] for r in rows]
        for _ in range(ticks):
            addend,rows,footer=native(kernel,bounds,rows,footer,7);delta=(delta+addend)%128;cases+=1
        expected,last,bulk=rule.delta(start,19,ticks)
        if (rows,footer,delta)!=(expected,last,bulk):raise ValueError('Bulk timer potential does not telescope')
        bulk_cases+=1
    return dict(game=game,rom_sha256=hashlib.sha256(rom).hexdigest(),entry_pc=bounds[0],exit_pc=bounds[1],
                rule=asdict(rule),refresh_modulus=128,native_cases=cases,bulk_compositions=bulk_cases,
                invariant='Timer refresh modulo128 equals per-tick baseline plus a linear timer potential difference and the number of positive footer ticks',
                limits='IRQ timer block only; remaining IRQ and main-thread components are not removed')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--roms',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);started=time.monotonic();rows=[]
    for game in rom_tables.LAYOUTS:
        row=audit(rom_tables.load(a.roms/(game+'.zip'),game),game,a.output/'build');rows.append(row)
        print(game,row['native_cases'],'timer transfers',row['rule'],flush=True)
    report=dict(cases=rows,native_cases=sum(r['native_cases'] for r in rows),seconds=time.monotonic()-started,
                peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                sources={n:hashlib.sha256((source_path(n)).read_bytes()).hexdigest() for n in
                         ('rom_timer_rules.py','rom_kernel.py','rom_kernel.c','rom_tables.py')})
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
