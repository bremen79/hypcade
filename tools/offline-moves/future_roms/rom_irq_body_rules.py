#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""US A-D normal-game IRQ body: RAM transfer and refresh potential.

Coin/service activity, the handler's mode bypass and watchdog expiry remain
outside this contract. E/F have different prescalers and are rejected. This
is a composable routine contract, not a whole-game timing proof.
"""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

from future_roms import rom_irq_rules
import rom_kernel
from future_roms import rom_sound_rules
import rom_tables
from future_roms import rom_timer_rules

ROOT = CORE
GAMES=('lair_a','lair_b','lair_c','lair_d')
TIMER=rom_timer_rules.TimerRule(46,42,(-21,-14,-6,2),-3)


def word(ram,at):
    return int.from_bytes(ram[at:at+2],'little')


def put_word(ram,at,value):
    ram[at:at+2]=value.to_bytes(2,'little')


class Rules:
    def __init__(self,rom,game):
        if game not in GAMES:raise ValueError('Normal IRQ body contract supports US A-D only')
        self.prefix=rom_irq_rules.Rules(rom,game)
        self.entry=self.prefix.core_entry
        body=bytearray(rom[self.entry:0x2772])
        # These two destinations are unreachable under the declared domain.
        for pc in (0x274c,0x2764):body[pc-self.entry:pc-self.entry+2]=b'\0\0'
        if self.entry!=0x266f or hashlib.sha256(body).hexdigest()!=\
                '9341683d066672f03822c667140fbac6cd9800c5b638233b09d5217a502a5eed':
            raise ValueError('Unknown US IRQ body instruction/branch structure')
        for lo,hi,expected in (
            (0x285f,0x287b,'b274b7c11c8864ebab1cdbc317070dd353e5b1bc5e6c475cb504d18c0fa57e59'),
            (0x28ec,0x290c,'52f9708de3b798be9f68120639176e022e8c9d4aa31c896c5a312e9c5e822363')):
            if hashlib.sha256(rom[lo:hi]).hexdigest()!=expected:raise ValueError('IRQ arithmetic/display helper changed')
        rom_timer_rules.validate_block(rom,rom_timer_rules.locate(rom))
        self.sound=rom_sound_rules.Rules(rom,game)

    def context(self,ram,iy=None):
        if len(ram)!=1024:raise ValueError('Expected 1 KiB board RAM')
        if ram[10]&32:raise ValueError('Mode-bypassed IRQ is outside normal gameplay contract')
        free=bool(ram[16]&16)
        if not free and ram[25]>(ram[16]&3)+1:
            raise ValueError('Pending coin award is outside normal gameplay contract')
        rows=[]
        if ram[8]&4:
            for n in range(17):
                at=0xe0+16*n
                if not ram[at]&128:break
                if n==16:raise ValueError('Descriptor count exceeds checked timer domain')
                rows.append(list(ram[at+12:at+16]))
            footer_at=0xe0+16*len(rows)
            if iy is not None and iy!=0xa000+footer_at:raise ValueError('IY does not identify the active footer')
            footer=word(ram,footer_at+14)
        else:footer_at=footer=0
        sound=rom_sound_rules.State(ram[28],word(ram,29),ram[27],ram[31])
        return free,rows,footer_at,footer,sound

    def body_potential(self,ram,iy=None):
        free,rows,_,footer,sound=self.context(ram,iy)
        baseline=129 if free else 194
        dynamic=self.sound.potential(sound)-3*word(ram,94)
        if ram[8]&4:
            baseline+=46+42*len(rows)
            dynamic+=TIMER.potential(rows)-3*footer
        return (baseline*word(ram,222)+dynamic)%128

    def total_potential(self,ram,state,iy=None):
        """Include hardware/vector/filter costs, without counting IRQs.

        Normal vectors use modulo 128. D uses scaled units modulo 17408:
        each whole IRQ's scaled refresh is potential(before)-potential(after).
        Main-thread writes are separate potential jumps.
        """
        body=self.body_potential(ram,iy);watchdog=word(ram,222)
        if not self.prefix.filtered:return (body+3*watchdog)%128
        prefix,_=self.prefix.core_potential(state)
        return (136*body+2140*watchdog+prefix)%(136*128)

    def parity_potential(self,ram,state,iy=None):
        """A two-valued correction conserved with R across whole normal IRQs.

        Free-play D needs only the filter's fifth counter; paid D needs its
        28-count counter. Normal free-play vectors need neither watchdog nor
        IRQ count. Window bytes disappear because their coefficients are even.
        """
        free,rows,_,footer,sound=self.context(ram,iy)
        value=self.sound.potential(sound)+word(ram,94)
        if ram[8]&4:value+=sum(row[0] for row in rows)+footer
        if self.prefix.filtered:value-=state.fifth if free else state.count
        elif not free:value+=word(ram,222)
        return value&1

    def step(self,ram,iy=None):
        free,rows,at,footer,sound=self.context(ram,iy)
        watchdog=word(ram,222)
        if not watchdog:raise ValueError('Expired watchdog is outside normal gameplay contract')
        after=bytearray(ram)
        after[10]|=64;after[32]|=16;after[26]&=~32
        if ram[8]&4:
            timers,last,timer_r=TIMER.delta(rows,footer)
            for n,row in enumerate(timers):after[0xec+16*n:0xf0+16*n]=bytes(row)
            put_word(after,at+14,last)
        else:timer_r=0
        current,sound_r=self.sound.step(sound)
        after[27]=current.duration;after[28]=current.flags
        put_word(after,29,current.pointer);after[31]=current.counter
        put_word(after,94,max(word(ram,94)-1,0));put_word(after,222,watchdog-1)
        refresh=((121 if free else 186)-3*int(word(ram,94)>0)+timer_r+sound_r)%128
        if refresh!=(self.body_potential(ram,iy)-self.body_potential(after,iy))%128:
            raise ValueError('IRQ body potential does not compose')
        return after,refresh


def audit(rom,game,build):
    rules=Rules(rom,game)
    # Memory-mapped input registers are external read-only fixture values.
    # The original ROM bytes are unchanged; no commercial file is written.
    image=bytearray(65536);image[:len(rom)]=rom;image[0xc010]=255
    kernel=rom_kernel.Kernel(image,build)
    cases=0
    def verify(ram):
        nonlocal cases
        _,rows,at,_,_=rules.context(ram)
        iy=0xa000+at if ram[8]&4 else 0xa200
        expected,refresh=rules.step(ram,iy)
        seed=127 if cases&1 else 0
        actual,regs=kernel.call(ram,rules.entry,iy=iy,refresh=seed)
        if actual[:0x3d0]!=expected[:0x3d0] or (regs['refresh']-seed)%128!=refresh or regs['observations']:
            changed=[hex(i) for i in range(0x3d0) if actual[i]!=expected[i]]
            raise ValueError('Original IRQ body differs: %s RAM=%s R=%s/%s' % (game,changed,(regs['refresh']-seed)%128,refresh))
        # Prefix/core composition is tested separately from the native body.
        # All native prefix states are covered by the physical phase audit.
        state=rom_irq_rules.State(cases%28,(cases//28)%5)
        prefix=rules.prefix.advance(state,1)
        end=expected if prefix.core_calls else ram
        scale=136 if rules.prefix.filtered else 1
        delta=prefix.refresh+(refresh if prefix.core_calls else 0)
        if (scale*delta-rules.total_potential(ram,state,iy)+rules.total_potential(end,prefix.state,iy))%(scale*128):
            raise ValueError('IRQ prefix and body potentials do not compose')
        if (delta-rules.parity_potential(ram,state,iy)+rules.parity_potential(end,prefix.state,iy))&1:
            raise ValueError('Reduced IRQ parity potential does not compose')
        cases+=1
    base=bytearray(1024);base[16]=16;put_word(base,222,2218)
    verify(base)
    # Every byte value in each non-timer/sound scalar read by the body. This
    # separates value-independent paths from their explicit branch classes.
    for free in (False,True):
        start=bytearray(base);start[16]=16 if free else 0
        for offset in (8,9,10,16,25,26,32):
            for value in range(256):
                ram=bytearray(start);ram[offset]=value
                if ram[10]&32:continue
                if not ram[16]&16 and ram[25]>(ram[16]&3)+1:continue
                verify(ram)
        for wait in (0,1,2,255,256,257,32768,65535):
            for watchdog in (1,2,255,256,257,2218,32768,65535):
                ram=bytearray(start);put_word(ram,94,wait);put_word(ram,222,watchdog);verify(ram)
        patterns=([0,0,0,0],[1,2,3,4],[0,1,2,3],[0,0,1,2],[0,0,0,1],[255,255,255,255])
        for count in range(17):
            for row in patterns:
                for footer in (0,1,256,65535):
                    ram,_=rom_timer_rules.memory([list(row) for _ in range(count)],footer)
                    ram[16]=start[16];ram[8]=4;put_word(ram,222,2218);put_word(ram,94,256);verify(ram)
        for pointer in sorted(rules.sound.cells):
            for counter in (0,1,2,255):
                for duration in (0,6,255):
                    ram=bytearray(start);ram[28]=255;put_word(ram,29,pointer)
                    ram[27]=duration;ram[31]=counter;verify(ram)
    return dict(game=game,native_cases=cases,core_entry=rules.entry,
        rom_sha256=hashlib.sha256(rom).hexdigest(),
        domain='No asserted coin/service inputs, mode bit clear, no pending coin award, positive watchdog',
        body_refresh='B - 3*[wait>0] + timer_transfer + sound_transfer; B=121 free / 186 paid',
        potential='watchdog * (B+8+enabled*(46+42*n)) + sound_phi + enabled*(timer_phi-3*footer) - 3*wait',
        limits='Normal-game IRQ routine contract and prefix composition; E/F and main-thread phase reachability remain separate')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--roms',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    started=time.monotonic();rows=[]
    for game in GAMES:
        rows.append(audit(rom_tables.load(args.roms/(game+'.zip'),game),game,args.output/'build'))
        print(game,rows[-1]['native_cases'],flush=True)
    report=dict(cases=rows,native_cases=sum(r['native_cases'] for r in rows),seconds=time.monotonic()-started,
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        sources={name:hashlib.sha256((source_path(name)).read_bytes()).hexdigest() for name in
            ('rom_irq_body_rules.py','rom_irq_rules.py','rom_sound_rules.py','rom_timer_rules.py','rom_kernel.py','rom_kernel.c','rom_tables.py')})
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
