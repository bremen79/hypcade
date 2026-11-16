#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact IRQ sound/countdown potential for the original Cine ROM programs.

The bytecode pointer only advances. Its remaining refresh cost is affine in
the inherited duration plus its nonzero indicator. External sound starts
appear as potential jumps; no assumed sound completion or phase law is needed.
"""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import argparse
from dataclasses import asdict,dataclass,replace
import hashlib
import json
from pathlib import Path
import resource
import time

import rom_kernel
import rom_tables

ROOT = CORE
ENTRY=bytes.fromhex('211ca0cb46c82e1f3e00bec02e1dcd')
COUNTER=bytes.fromhex('211fa03e00be280135')
BODY_HASH='54639ffe32c1c1712c57438dd75987cb30c41df9f5a9ba94899eb8b2c31be73f'
HELPER_HASH='ab702baf4ab3883c12b10af7c5801b8765d60536afef09a5399c816038cfaeb5'
START_HASH='2637b1fdc4eb203d62534bb915ec0e29ae3f35e4e4ac228839ac2eb5de648ba5'


@dataclass(frozen=True)
class State:
    flags: int
    pointer: int
    duration: int
    counter: int

    def __post_init__(self):
        if any(type(v) is not int or not 0<=v<=255 for v in (self.flags,self.duration,self.counter)):
            raise ValueError('Sound fields must be bytes')
        if type(self.pointer) is not int or not 0<=self.pointer<=65535:raise ValueError('Invalid sound pointer')


@dataclass(frozen=True)
class Cell:
    pointer: int
    header: int
    reload: object
    following: object
    mixer: bool
    end: int

    @property
    def m1(self):
        h=self.header
        # Includes the indirect pointer helper and all CALL/RET fetches.
        return (71+10*(2*(h&3)+((h>>2)&3))+16*bool(h&32)+3*bool(h&16)
                +26*bool(h&64)+7*self.mixer+4*bool(h&128)+6*(self.following is not None))


def decode(rom,pointer,boundary=None):
    limit=len(rom) if boundary is None else boundary
    if not 0<=pointer<limit<=len(rom):raise ValueError('Sound pointer outside immutable ROM')
    q=pointer+1;h=rom[pointer]
    q+=2*(h&3)+int(bool(h&32))+((h>>2)&3)
    if q>=limit:raise ValueError('Sound payload crosses its ROM boundary')
    duration=rom[q] if h&16 else None;q+=int(bool(h&16))+2*int(bool(h&64))
    if q>=limit:raise ValueError('Sound payload crosses its ROM boundary')
    mixer=bool(rom[q]&128);q+=int(mixer)
    if q>=limit:raise ValueError('Missing sound continuation/end byte')
    return Cell(pointer,h,duration,q+1 if rom[q]&32 else None,mixer,q+1)


def locate(rom):
    entry=rom.find(ENTRY);counter=rom.find(COUNTER)
    if min(entry,counter)<0:raise ValueError('Unknown original sound/counter routine')
    body=bytearray(rom[entry:entry+143]);calls={}
    for at in (15,31,42,55,90,128):
        calls[at]=rom_tables.word(rom,entry+at);body[at:at+2]=b'\0\0'
    helper=bytearray(rom[entry+143:entry+161]);helper[2:4]=b'\0\0'
    start=bytearray(rom[entry+161:entry+188]);table=rom_tables.word(rom,entry+162);start[1:3]=b'\0\0'
    if tuple(hashlib.sha256(v).hexdigest() for v in (body,helper,start))!=(BODY_HASH,HELPER_HASH,START_HASH):
        raise ValueError('Original sound instruction/branch structure changed')
    if any(calls[at]!=entry+143 for at in (31,42,55,90)):raise ValueError('Unknown sound payload helper')
    if rom_tables.word(rom,entry+145)!=entry+160:raise ValueError('Sound payload exit moved')
    pointer=calls[15]
    if rom[pointer:pointer+4]!=bytes.fromhex('5e2356cd') or rom[pointer+6]!=0xc9:
        raise ValueError('Unknown sound pointer helper')
    copy=rom_tables.word(rom,pointer+4)
    if rom[copy:copy+3]!=bytes.fromhex('d5e1c9') or rom[calls[128]:calls[128]+3]!=bytes.fromhex('e5c1c9'):
        raise ValueError('Unknown sound register-copy helper')
    return entry,counter,entry+161,table


class Rules:
    def __init__(self,rom,game):
        self.rom=rom;self.entry,self.counter_entry,self.start_entry,self.table=locate(rom)
        self.roots=tuple(rom_tables.word(rom,self.table+2*i) for i in range(4))
        if self.roots[0]!=self.table+8 or sorted(set(self.roots))!=list(self.roots):
            raise ValueError('Unknown four-program sound inventory')
        limit=rom_tables.LAYOUTS[game]['roots'];self.cells={}
        for i,root in enumerate(self.roots):
            boundary=self.roots[i+1] if i<3 else limit
            p=root
            while True:
                cell=decode(rom,p,boundary);self.cells[p]=cell
                if cell.following is None:
                    if cell.end!=boundary:raise ValueError('Unparsed bytes in complete sound inventory')
                    break
                if cell.following<=p or cell.following>=boundary:raise ValueError('Sound bytecode is not a forward DAG')
                p=cell.following
        self.program_cells=set(self.cells)
        # The main thread writes the pointer in two bytes without DI. Close
        # the potential domain under each byte write and each IRQ advance.
        # This conservative closure covers arbitrarily interleaved writes;
        # it is NOT a claim that every such timing is physically reachable.
        pending=list(self.cells)
        for p in pending:
            cell=self.cells[p]
            targets=[cell.following]
            targets.extend((p&0xff00)|(root&255) for root in self.roots)
            targets.extend((root&0xff00)|(p&255) for root in self.roots)
            for target in targets:
                if target is not None and target not in self.cells:
                    self.cells[target]=decode(rom,target);pending.append(target)
        self.coefficients={}
        for p,cell in sorted(self.cells.items(),reverse=True):
            if cell.reload is not None:
                d=cell.reload
                tail=d if cell.following is None else 5*d-4*bool(d)+self.remaining(cell.following,d)
                value=(0,0,cell.m1-4+tail)
            elif cell.following is None:value=(1,0,cell.m1-4)
            else:
                a,b,c=self.coefficients[cell.following];value=(5+a,-4+b,cell.m1-4+c)
            self.coefficients[p]=value

    def remaining(self,pointer,duration):
        a,b,c=self.coefficients[pointer]
        return (a*duration+b*bool(duration)+c)%128

    def potential(self,state):
        if not state.flags&1:return state.counter%128
        if state.pointer not in self.cells:raise ValueError('Active sound pointer outside the decoded inventory')
        return (5*state.counter-4*bool(state.counter)+self.remaining(state.pointer,state.duration))%128

    def interpret(self,state):
        if not state.flags&1:return state,4
        if state.pointer not in self.cells:raise ValueError('Unknown active sound pointer')
        if state.counter:return state,8
        cell=self.cells[state.pointer];duration=state.duration if cell.reload is None else cell.reload
        return State(state.flags if cell.following is not None else state.flags&254,
                     state.pointer if cell.following is None else cell.following,duration,duration),cell.m1

    def step(self,state):
        after,delta=self.interpret(replace(state,counter=max(state.counter-1,0)))
        return after,delta+4+int(state.counter>0)

    def advance(self,state,ticks):
        if type(ticks) is not int or ticks<0:raise ValueError('Expected nonnegative IRQ count')
        original=state;remaining=ticks
        while remaining:
            if not state.flags&1:
                state=replace(state,counter=max(state.counter-remaining,0));break
            if state.counter>1:
                skip=min(remaining,state.counter-1);state=replace(state,counter=state.counter-skip);remaining-=skip
                if not remaining:break
            state,_=self.step(state);remaining-=1
        return state,(8*ticks+self.potential(original)-self.potential(state))%128

    def start(self,state,program):
        if type(program) is not int or not 0<=program<4:raise ValueError('Unknown sound program')
        after=replace(state,flags=state.flags|1,pointer=self.roots[program])
        return after,(self.potential(after)-self.potential(state))%128


def memory(state):
    ram=bytearray(1024);ram[0x1b]=state.duration;ram[0x1c]=state.flags
    ram[0x1d:0x1f]=state.pointer.to_bytes(2,'little');ram[0x1f]=state.counter
    return ram


def from_ram(ram):
    return State(ram[0x1c],int.from_bytes(ram[0x1d:0x1f],'little'),ram[0x1b],ram[0x1f])


def native(kernel,rules,state,seed=0):
    ram=memory(state)
    middle,regs=kernel.call(ram,rules.counter_entry,stop=rules.counter_entry+9,refresh=seed)
    reads,writes=kernel.access()
    if reads!={0x1f} or any(a!=0x1f and a<0x3d0 for a in writes) or regs['observations']:
        raise ValueError('Sound countdown accesses undeclared state')
    after,final=kernel.call(middle,rules.entry,refresh=regs['refresh'])
    expected,delta=rules.step(state)
    if after[:0x3d0]!=memory(expected)[:0x3d0] or final['observations']:
        raise ValueError('Sound execution mutates undeclared RAM or reads R')
    reads,writes=kernel.access();allowed={0x1c}
    if state.flags&1:
        allowed.add(0x1f)
        if not middle[0x1f]:
            allowed.update((0x1d,0x1e))
            if rules.cells[state.pointer].reload is None:allowed.add(0x1b)
    if {a for a in reads if a<0x3d0}!=allowed or any(a<0x3d0 and a not in range(0x1b,0x20) for a in writes):
        raise ValueError('Sound interpreter accesses undeclared state')
    if (final['refresh']-seed)%128!=delta%128:
        raise ValueError('Literal sound fetch counts differ from original CPU')
    if delta%128!=(8+rules.potential(state)-rules.potential(expected))%128:
        raise ValueError('Sound state potential does not telescope')
    return expected,delta%128


def audit(rom,game,build):
    rules=Rules(rom,game);kernel=rom_kernel.Kernel(rom,build);cases=0;starts=0
    def verify(state,seed=0):
        nonlocal cases
        result=native(kernel,rules,state,seed);cases+=1;return result
    for flags in (0,254):
        for counter in range(256):
            for seed in (0,127):verify(State(flags,0,173,counter),seed)
    for counter in range(2,256):
        for flags in (1,255):verify(State(flags,rules.roots[0],173,counter),127)
    for cell in rules.cells.values():
        for counter in (0,1):
            for duration in (range(256) if cell.reload is None else (173,)):
                for seed in (0,127):verify(State(1,cell.pointer,duration,counter),seed)
    for flags in range(256):
        for counter in (0,17):verify(State(flags,rules.roots[1],6,counter),255)
    # Program start retains both the old duration and residual countdown.
    for active in (0,1):
        for pointer in rules.cells:
            for counter in (0,1,6,255):
                for program in range(4):
                    state=State(active,pointer,17,counter);expected,_=rules.start(state,program)
                    after,regs=kernel.call(memory(state),rules.start_entry+12,hl=rules.table+2*program)
                    if after[:0x3d0]!=memory(expected)[:0x3d0] or regs['refresh']!=9:
                        raise ValueError('Original sound start changes more than pointer/active flag')
                    starts+=1
    state=State(0,0,173,255)
    callsite=rom.find(bytes((0x3e,0,0xcd,rules.start_entry&255,rules.start_entry>>8)))
    if callsite<0:raise ValueError('Missing original immediate sound-zero call')
    after,regs=kernel.call(memory(state),callsite,stop=callsite+5)
    if after[:0x3d0]!=memory(rules.start(state,0)[0])[:0x3d0] or regs['refresh']!=19:
        raise ValueError('Complete sound start differs from the literal 17-fetch rule')
    starts+=1
    bulk=0
    for program in range(4):
        for ticks in (0,1,2,7,13,31,255):
            start=State(1,rules.roots[program],17,6);state=start;total=0
            for _ in range(ticks):state,add=verify(state,127);total=(total+add)%128
            expected,delta=rules.advance(start,ticks)
            if (state,total)!=(expected,delta):raise ValueError('Bulk sound potential differs from sequential original updates')
            bulk+=1
    # Overwriting a sound is a potential jump, not an assumed completed chirp.
    state=State(0,0,0,0);initial=rules.potential(state);jumps=total=0
    for tick in range(32):
        if tick in (0,2,5,10,20):
            state,jump=rules.start(state,(tick//2)%4);jumps+=jump
        state,add=verify(state);total+=add
    if total%128!=(8*32+initial-rules.potential(state)+jumps)%128:raise ValueError('Interrupted sound composition differs')
    return dict(game=game,native_cases=cases,native_start_cases=starts,bulk_compositions=bulk,
        original_program_cells=len(rules.program_cells),potential_domain_cells=len(rules.cells),
        sound_entry=rules.entry,counter_entry=rules.counter_entry,start_entry=rules.start_entry,
        program_roots=list(rules.roots),cells=[asdict(v)|dict(m1=v.m1,remaining_coefficients=rules.coefficients[p]) for p,v in sorted(rules.cells.items())],
        formula='8*N + Phi(before) - Phi(after), modulo128; add each external start potential jump',
        rom_sha256=hashlib.sha256(rom).hexdigest(),
        limits='IRQ sound routine plus its countdown block; byte-write closure is conservative, not timing reachability. IRQ CALL, other IRQ work and main-thread start fetches remain separate')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--roms',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    started=time.monotonic();rows=[]
    for game in rom_tables.LAYOUTS:
        row=audit(rom_tables.load(a.roms/(game+'.zip'),game),game,a.output/'build');rows.append(row)
        print(game,row['native_cases'],'sound transfers;',row['native_start_cases'],'start cases',flush=True)
    report=dict(cases=rows,native_cases=sum(r['native_cases'] for r in rows),native_start_cases=sum(r['native_start_cases'] for r in rows),
        seconds=time.monotonic()-started,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        sources={n:hashlib.sha256((source_path(n)).read_bytes()).hexdigest() for n in
                 ('rom_sound_rules.py','rom_kernel.py','rom_kernel.c','rom_tables.py')})
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
