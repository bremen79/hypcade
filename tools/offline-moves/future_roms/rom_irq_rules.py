#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cine IRQ entry transfer, including revision D's periodic core filter.

Only hardware acceptance and the ROM prefix are counted. Enabled core-handler
work is separate. No external refresh-phase distribution is assumed.
"""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

from dataclasses import dataclass
import hashlib

import rom_tables


@dataclass(frozen=True)
class State:
    count: int=0
    fifth: int=0

    def __post_init__(self):
        if type(self.count) is not int or not 0<=self.count<28 or type(self.fifth) is not int or not 0<=self.fifth<5:
            raise ValueError('Expected a canonical revision-D IRQ-filter state')


@dataclass(frozen=True)
class Transfer:
    state: State
    core_calls: int
    refresh: int
    cycles: int


class Rules:
    def __init__(self,rom,game):
        if rom[0x38]!=0xc3:raise ValueError('Unknown Cine IRQ vector')
        vector=rom_tables.word(rom,0x39);self.filtered=game=='lair_d'
        if self.filtered:
            if vector!=0x9fd0 or hashlib.sha256(rom[vector:0x9ff9]).hexdigest()!=\
                    'fe35b58f8fa309a41191a9d50efe74ffc5dd639657205b77a95357d677d9b6f2':
                raise ValueError('Unknown revision-D IRQ filter')
            vector=0x2000
        if rom[vector]!=0xc3:raise ValueError('Unknown core-handler jump')
        self.core_entry=rom_tables.word(rom,vector+1)

    def advance(self,state,count):
        if type(count) is not int or count<0:raise ValueError('Expected a nonnegative accepted-IRQ count')
        if not self.filtered:return Transfer(state,count,(3*count)%128,33*count)
        wraps=(state.count+count)//28
        fifths=(state.fifth+wraps)//5
        after=State((state.count+count)%28,(state.fifth+wraps)%5)
        # Includes one hardware acknowledge (1 fetch/13 T-states). Ordinary
        # prefix: 15/145; wrap skipped: 23/204; fifth wrap enabled: 23/212.
        return Transfer(after,count-wraps+fifths,(15*count+8*wraps)%128,
                        145*count+59*wraps+8*fifths)

    def refresh_potential(self,state):
        return (110*state.count)%128 if self.filtered else 0

    def core_potential(self,state):
        """Exact prefix accounting in units of enabled core-handler calls.

        For D, 136*prefix_R = 2140*core_calls + Phi(before)-Phi(after)
        (modulo 136*128), and the clock identity is exact with coefficient
        20603. Thus a watchdog counting core calls can replace the IRQ count.
        Ordinary vectors have scale one and per-core coefficients 3 and 33.
        """
        if not self.filtered:
            return 0,0
        index=28*state.fifth+state.count
        wraps=index//28
        core=index-wraps
        refresh=15*index+8*wraps
        cycles=145*index+59*wraps
        return 2140*core-136*refresh,20603*core-136*cycles
