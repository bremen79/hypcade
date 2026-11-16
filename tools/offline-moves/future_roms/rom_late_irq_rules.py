#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""US E/F normal IRQ contracts with exact timer/handler prescalers.

The counters are ROM state, not stochastic transitions. Released coin inputs,
inactive service, no pending credit award and a positive watchdog are explicit
preconditions. Mode-bypassed/disabled handlers and F's latched coin releases
remain outside this contract. No whole-game phase reachability is claimed.
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
from future_roms import rom_irq_body_rules
import rom_kernel
from future_roms import rom_sound_rules
import rom_tables
from future_roms import rom_timer_rules

from future_roms.rom_irq_body_rules import word,put_word,TIMER

ROOT = CORE
GAMES=('lair_e','lair_f')
LAYOUTS={
 'lair_e':dict(entry=0x17b3,sound=0x18c5,counter=0x5a,dec=0x19b2,display=0x1a69,
    body_hash='88ab43277219848dde2333a867a3e0ac20324edc6bbbfa27f9be3100556f758f',
    dec_hash='38201ba53846218cdd3ae1831a30a7a1adde3dd9a75e9d7b892ba25f020857ed',
    display_hash='b162a2fd6e10ea9599953776e126df541810ffb4353ec66ab06bf19492c3456d'),
 'lair_f':dict(entry=0x1820,sound=0x19fa,counter=0,dec=0x1ae7,display=0x1b9e,
    body_hash='c645c011b4545faaa22c2d4eea72845b1b3d14621cdf490d842954ab1a14587a',
    dec_hash='af2bddd4a6d2afda18c601f336e1f4e6b3b26ce06a15c2b5c4f5477f685a3114',
    display_hash='9960cdbc00678b46904b6f02dfbc58a4bcca5fcf375dc085c992fc0ff6ef2306'),
}


class Rules:
    def __init__(self,rom,game):
        if game not in GAMES:raise ValueError('Late IRQ rules support US E/F only')
        self.game=game;self.spec=LAYOUTS[game];self.entry=self.spec['entry']
        self.prefix=rom_irq_rules.Rules(rom,game)
        for start,end,key in ((self.entry,self.spec['sound'],'body_hash'),
            (self.spec['dec'],self.spec['dec']+28,'dec_hash'),
            (self.spec['display'],self.spec['display']+32,'display_hash')):
            if hashlib.sha256(rom[start:end]).hexdigest()!=self.spec[key]:
                raise ValueError('Late IRQ instruction/branch structure changed')
        if self.prefix.core_entry!=self.entry:raise ValueError('Unexpected late IRQ vector')
        rom_timer_rules.validate_block(rom,rom_timer_rules.locate(rom))
        self.sound=rom_sound_rules.Rules(rom,game)

    @property
    def is_f(self):return self.game=='lair_f'

    def context(self,ram,iy=None):
        if len(ram)!=1024:raise ValueError('Expected 1 KiB board RAM')
        if ram[10]&32:raise ValueError('Mode-bypassed IRQ outside late normal-game contract')
        if self.is_f and not ram[1]&4:raise ValueError('Disabled IRQ outside late normal-game contract')
        if self.is_f and ram[26]&192:raise ValueError('Latched coin release outside late normal-game contract')
        free=bool(ram[16]&16)
        if not free and ram[25]>(ram[16]&1)+1:raise ValueError('Pending coin award outside late normal-game contract')
        enabled=bool(ram[8]&4);rows=[];at=footer=0
        period=31 if not self.is_f or ram[1]&1 else 255
        if enabled:
            counter=ram[self.spec['counter']]
            if counter>=period:raise ValueError('Noncanonical timer prescaler outside late normal-game contract')
            for n in range(17):
                at=0xe0+16*n
                if not ram[at]&128:break
                if n==16:raise ValueError('Too many timer descriptors')
                rows.append(list(ram[at+12:at+16]))
            at=0xe0+16*len(rows)
            if iy is not None and iy!=0xa000+at:raise ValueError('IY does not identify the active footer')
            footer=word(ram,at+14)
        sound=rom_sound_rules.State(ram[28],word(ram,29),ram[27],ram[31])
        return free,enabled,rows,at,footer,period,sound

    def pulse_potential(self,ram):
        count=ram[93]
        return 12*count-4*int(count>0 and bool(ram[32]&16)) if self.is_f else 0

    def body_potential(self,ram,iy=None):
        free,enabled,rows,_,footer,period,sound=self.context(ram,iy)
        baseline=(151 if free else 216) if self.is_f else (129 if free else 194)
        dynamic=self.sound.potential(sound)-3*word(ram,94)+self.pulse_potential(ram)
        # In F, seven of eight calls can return before any countdown work.
        # The raw byte wraps at 256, a multiple of the refresh modulus.
        divided=self.is_f and bool(ram[1]&8)
        if divided:baseline+=5-57;dynamic-=57*ram[92]
        if enabled:
            timer_base=46+42*len(rows)
            correction=((3-timer_base)*pow(period,-1,128))%128
            gate=11+int(bool(ram[1]&1)) if self.is_f else 6
            baseline+=gate+timer_base+correction
            dynamic+=correction*ram[self.spec['counter']]+TIMER.potential(rows)-3*footer
        return (baseline*word(ram,222)+dynamic)%128

    def total_potential(self,ram,state=None,iy=None):
        body=self.body_potential(ram,iy)
        # All these vectors cost three fetches per accepted IRQ. With the
        # eight-divider, the raw counter counts those IRQs modulo 256.
        return (body-3*ram[92] if self.is_f and ram[1]&8 else body+3*word(ram,222))%128

    def parity_potential(self,ram,state=None,iy=None):
        return self.total_potential(ram,state,iy)&1

    def step(self,ram,iy=None):
        free,enabled,rows,at,footer,period,sound=self.context(ram,iy)
        watchdog=word(ram,222)
        if not watchdog:raise ValueError('Expired watchdog outside late normal-game contract')
        after=bytearray(ram);after[10]|=64
        divided=self.is_f and bool(ram[1]&8)
        if self.is_f:
            after[76]=after[77]=0
            if divided:
                after[92]=(ram[92]+1)&255
                if after[92]&7:
                    return after,57
        else:after[26]&=~32
        pulse_extra=0
        if self.is_f and ram[93]>0:
            if ram[32]&16:
                after[93]-=1;after[32]&=~16;pulse_extra=8
            else:after[32]|=16;pulse_extra=4
        else:after[32]|=16
        timer_r=0
        if enabled:
            current=ram[self.spec['counter']]+1;skip=current==period
            after[self.spec['counter']]=0 if skip else current
            timer_r=(11+int(bool(ram[1]&1)) if self.is_f else 6)+3*skip
            if not skip:
                timers,last,delta=TIMER.delta(rows,footer);timer_r+=delta
                for n,row in enumerate(timers):after[0xec+16*n:0xf0+16*n]=bytes(row)
                put_word(after,at+14,last)
        current,sound_r=self.sound.step(sound)
        after[27]=current.duration;after[28]=current.flags;put_word(after,29,current.pointer);after[31]=current.counter
        put_word(after,94,max(0,word(ram,94)-1));put_word(after,222,watchdog-1)
        baseline=(143 if free else 208) if self.is_f else (121 if free else 186)
        refresh=(baseline+5*divided+pulse_extra-3*int(word(ram,94)>0)+timer_r+sound_r)%128
        return after,refresh


def audit(rom,game,build):
    rules=Rules(rom,game);image=bytearray(65536);image[:len(rom)]=rom;image[0xc010]=255
    kernel=rom_kernel.Kernel(image,build);cases=0
    def verify(ram):
        nonlocal cases
        _,enabled,_,at,_,_,_=rules.context(ram)
        iy=0xa000+at if enabled else 0xa200
        expected,refresh=rules.step(ram,iy);seed=127 if cases&1 else 0
        actual,regs=kernel.call(ram,rules.entry,iy=iy,refresh=seed)
        if expected[:0x3d0]!=actual[:0x3d0] or (regs['refresh']-seed)%128!=refresh or regs['observations']:
            changed=[hex(i) for i in range(0x3d0) if expected[i]!=actual[i]]
            raise ValueError('Late original IRQ differs: %s RAM=%s R=%s/%s' % (game,changed,(regs['refresh']-seed)%128,refresh))
        if (rules.body_potential(ram,iy)-rules.body_potential(expected,iy)-refresh)%128:
            raise ValueError('Late body potential differs')
        if (rules.total_potential(ram,iy=iy)-rules.total_potential(expected,iy=iy)-refresh-3)%128:
            raise ValueError('Late full IRQ potential differs')
        cases+=1
    modes=(4,5,12,13) if rules.is_f else (0,)
    base=bytearray(1024);base[16]=16;put_word(base,222,2218)
    for mode in modes:
      for free in (False,True):
        start=bytearray(base);start[1]=mode;start[16]=16 if free else 0;verify(start)
        for offset in (1,8,9,10,16,25,26,32,76,77,92,93):
            for value in range(256):
                ram=bytearray(start);ram[offset]=value
                try:rules.context(ram)
                except ValueError:continue
                verify(ram)
        for wait in (0,1,255,256,65535):
            for watchdog in (1,255,256,65535):
                ram=bytearray(start);put_word(ram,94,wait);put_word(ram,222,watchdog);verify(ram)
        period=31 if not rules.is_f or mode&1 else 255
        # Every prescaler phase at the wrap boundary and every 8-divider
        # phase, with genuine timer/sound work waiting behind the gates.
        for counter in range(period):
          for divider in range(8) if rules.is_f else (0,):
            ram,_=rom_timer_rules.memory([[1,2,3,4]],256)
            ram[1]=mode;ram[8]=4;ram[16]=start[16];ram[92]=divider
            ram[rules.spec['counter']]=counter;put_word(ram,222,2218);verify(ram)
        patterns=([0,0,0,0],[1,2,3,4],[0,1,2,3],[0,0,1,2],[0,0,0,1],[255,255,255,255])
        for count in range(17):
          for row in patterns:
            for counter in (0,period-1):
              for footer in (0,1,256,65535):
                ram,_=rom_timer_rules.memory([list(row) for _ in range(count)],footer)
                ram[1]=mode;ram[8]=4;ram[16]=start[16];ram[92]=7
                ram[rules.spec['counter']]=counter;put_word(ram,222,2218);put_word(ram,94,256);verify(ram)
        for pointer in rules.sound.cells:
          for counter in (0,1,2,255):
            ram=bytearray(start);ram[92]=7;ram[28]=255;put_word(ram,29,pointer);ram[27]=6;ram[31]=counter;verify(ram)
        for pulse in range(256) if rules.is_f else (0,):
          for marker in (0,16):
            ram=bytearray(start);ram[92]=7;ram[93]=pulse;ram[32]=marker;verify(ram)
    return dict(game=game,native_cases=cases,rom_sha256=hashlib.sha256(rom).hexdigest(),
        timer_periods=[31,255] if rules.is_f else [31],handler_dividers=[1,8] if rules.is_f else [1],
        scope='Normal released-coin IRQ RAM/refresh contract and modular potential; exceptional paths remain explicit')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--roms',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True);started=time.monotonic();rows=[]
    for game in GAMES:
        rows.append(audit(rom_tables.load(args.roms/(game+'.zip'),game),game,args.output/'build'))
        print(game,rows[-1]['native_cases'],flush=True)
    report=dict(cases=rows,native_cases=sum(r['native_cases'] for r in rows),seconds=time.monotonic()-started,
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        sources={name:hashlib.sha256((source_path(name)).read_bytes()).hexdigest() for name in
            ('rom_late_irq_rules.py','rom_irq_body_rules.py','rom_irq_rules.py','rom_sound_rules.py','rom_timer_rules.py','rom_kernel.py','rom_kernel.c','rom_tables.py')})
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
