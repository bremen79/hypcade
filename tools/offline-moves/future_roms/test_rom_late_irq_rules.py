#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic late-board prescaler and modular-potential checks."""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import unittest

from future_roms import rom_late_irq_rules as late
from future_roms import rom_irq_rules
from future_roms import rom_timer_rules
from future_roms.test_rom_sound_rules import sound


def rules(game):
    value=object.__new__(late.Rules);value.game=game;value.spec=late.LAYOUTS[game]
    value.sound=sound();value.prefix=object.__new__(rom_irq_rules.Rules);value.prefix.filtered=False
    return value


def ram(mode=5):
    value=bytearray(1024);value[1]=mode;value[16]=16;late.put_word(value,222,2218)
    return value


class LateIRQTest(unittest.TestCase):
    def test_e_skips_only_the_thirty_first_timer_update(self):
        r=rules('lair_e');before,iy=rom_timer_rules.memory([[1,2,3,4]],256)
        before[16]=16;before[8]=4;late.put_word(before,222,100)
        for count in (0,29,30):
            before[90]=count;after,delta=r.step(before,iy)
            self.assertEqual(after[90],(count+1)%31)
            self.assertEqual(list(after[0xec:0xf0]),[1 if count==30 else 0,2,3,4])
            self.assertEqual(late.word(after,0xfe),256 if count==30 else 255)
            self.assertEqual(delta,(129+9 if count==30 else 129+6+46+42-21-3)%128)

    def test_f_early_return_does_not_run_sound_or_countdowns(self):
        r=rules('lair_f');before=ram(13);before[92]=0;before[31]=7
        late.put_word(before,94,20);before[76]=255;before[77]=255
        after,delta=r.step(before)
        self.assertEqual(delta,57)
        self.assertEqual((after[92],after[76],after[77],after[31]),(1,0,0,7))
        self.assertEqual(late.word(after,222),2218)
        self.assertEqual(late.word(after,94),20)
        before[92]=255;after,delta=r.step(before)
        self.assertEqual(after[92],0)
        self.assertEqual(late.word(after,222),2217)
        self.assertEqual(after[31],6)

    def test_f_both_timer_periods(self):
        r=rules('lair_f')
        for mode,period in ((4,255),(5,31)):
            before,iy=rom_timer_rules.memory([[0,1,2,3]],1)
            before[1]=mode;before[8]=4;before[16]=16;before[0]=period-1
            late.put_word(before,222,10)
            after,_=r.step(before,iy)
            self.assertEqual(after[0],0)
            self.assertEqual(after[0xed],1)
            self.assertEqual(late.word(after,0xfe),1)

    def test_pending_pulse_completes_in_two_deep_calls(self):
        r=rules('lair_f');before=ram();before[93]=2;before[32]=0
        middle,first=r.step(before);after,second=r.step(middle)
        self.assertEqual((middle[93],middle[32]&16),(2,16))
        self.assertEqual((after[93],after[32]&16),(1,0))
        self.assertEqual((first+second-2*151)%128,12)
        self.assertEqual(r.pulse_potential(before)-r.pulse_potential(after),12)

    def test_full_irq_potential_over_prescaler_boundaries(self):
        for game in late.GAMES:
            r=rules(game)
            for mode in (4,5,12,13):
                period=31 if game=='lair_e' or mode&1 else 255
                for count in (0,period-2,period-1):
                    for divider in (0,6,7,255):
                        before,iy=rom_timer_rules.memory([[2,3,4,5]],300)
                        before[1]=mode;before[8]=4;before[16]=16;before[92]=divider
                        before[r.spec['counter']]=count;late.put_word(before,222,20)
                        after,delta=r.step(before,iy)
                        self.assertEqual((r.body_potential(before,iy)-r.body_potential(after,iy)-delta)%128,0)
                        self.assertEqual((r.total_potential(before,iy=iy)-r.total_potential(after,iy=iy)-delta-3)%128,0)

    def test_contract_rejects_exceptional_paths(self):
        r=rules('lair_f');before=ram(0)
        with self.assertRaisesRegex(ValueError,'Disabled IRQ'):r.step(before)
        before=ram();before[26]=128
        with self.assertRaisesRegex(ValueError,'Latched coin'):r.step(before)
        before=ram();before[8]=4;before[0]=31
        with self.assertRaisesRegex(ValueError,'Noncanonical'):r.step(before)
        before=ram();before[16]=2;before[25]=2
        # E/F price uses bit zero only; A-D's two-bit mask would accept this.
        with self.assertRaisesRegex(ValueError,'Pending coin'):r.step(before)


if __name__=='__main__':unittest.main()
