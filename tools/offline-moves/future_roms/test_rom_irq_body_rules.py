#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small synthetic RAM states for the normal IRQ body's composition contract."""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import unittest

from future_roms import rom_irq_body_rules as body
from future_roms import rom_irq_rules
from future_roms import rom_timer_rules
from future_roms.test_rom_sound_rules import sound


def rules(filtered=False):
    value=object.__new__(body.Rules);value.sound=sound()
    value.prefix=object.__new__(rom_irq_rules.Rules);value.prefix.filtered=filtered
    return value


def ram():
    value=bytearray(1024);value[16]=16;body.put_word(value,222,2218)
    return value


class IRQBodyTest(unittest.TestCase):
    def test_free_and_paid_display_costs(self):
        r=rules();before=ram();before[26]=255
        after,delta=r.step(before)
        self.assertEqual(delta,129%128)
        self.assertEqual((after[10],after[26],after[32]),(64,223,16))
        self.assertEqual(body.word(after,222),2217)
        before[16]=0
        self.assertEqual(r.step(before)[1],194%128)

    def test_wait_and_watchdog_word_boundaries(self):
        r=rules()
        for wait in (0,1,255,256,65535):
            for watchdog in (1,256,65535):
                before=ram();body.put_word(before,94,wait);body.put_word(before,222,watchdog)
                after,delta=r.step(before)
                self.assertEqual(body.word(after,94),max(0,wait-1))
                self.assertEqual(body.word(after,222),watchdog-1)
                self.assertEqual(delta,(129-3*bool(wait))%128)

    def test_enabled_timer_and_zero_footer(self):
        r=rules();before,iy=rom_timer_rules.memory([[1,2,3,4]],0)
        before[8]=4;before[16]=16;body.put_word(before,222,12)
        after,delta=r.step(before,iy)
        # Taking the first delay path saves 21 fetches against scanning an
        # exhausted descriptor's four zero bytes.
        self.assertEqual(delta,(129+46+42-21)%128)
        self.assertEqual(list(after[0xec:0xf0]),[0,2,3,4])
        self.assertEqual(body.word(after,(iy-0xa000)+14),0)

    def test_sound_start_and_end_retain_fields(self):
        r=rules();before=ram();before[28]=255;body.put_word(before,29,13)
        before[27]=6;before[31]=1
        after,delta=r.step(before)
        self.assertEqual(delta,(121+76)%128)
        self.assertEqual((after[28],body.word(after,29),after[27],after[31]),(254,13,6,6))

    def test_total_potential_handles_skipped_core_calls(self):
        r=rules(True)
        for count in range(28):
            for fifth in range(5):
                before=ram();state=rom_irq_rules.State(count,fifth)
                prefix=r.prefix.advance(state,1)
                after,delta=r.step(before) if prefix.core_calls else (before,0)
                change=r.total_potential(before,state)-r.total_potential(after,prefix.state)
                self.assertEqual((change-136*(prefix.refresh+delta))%(136*128),0)

    def test_reduced_parity_ignores_window_values_and_free_play_watchdog(self):
        r=rules(True);before,iy=rom_timer_rules.memory([[0,2,3,4]],256)
        before[8]=4;before[16]=16;body.put_word(before,222,256)
        state=rom_irq_rules.State(27,2)
        original=r.parity_potential(before,state,iy)
        changed=bytearray(before);changed[0xed:0xf0]=bytes((255,0,1));body.put_word(changed,222,1)
        self.assertEqual(r.parity_potential(changed,state,iy),original)
        for filtered in (False,True):
            r.prefix.filtered=filtered
            for free in (False,True):
                before[16]=16 if free else 0
                for count in range(28):
                    for fifth in range(5):
                        state=rom_irq_rules.State(count,fifth);prefix=r.prefix.advance(state,1)
                        after,delta=r.step(before,iy) if prefix.core_calls else (before,0)
                        self.assertEqual((prefix.refresh+delta-r.parity_potential(before,state,iy)+
                                          r.parity_potential(after,prefix.state,iy))&1,0)

    def test_out_of_contract_states_fail(self):
        r=rules()
        before=ram();before[10]=32
        with self.assertRaisesRegex(ValueError,'Mode-bypassed'):r.step(before)
        before=ram();before[16]=0;before[25]=2
        with self.assertRaisesRegex(ValueError,'Pending coin'):r.step(before)
        before=ram();body.put_word(before,222,0)
        with self.assertRaisesRegex(ValueError,'Expired watchdog'):r.step(before)
        before=ram();before[8]=4
        with self.assertRaisesRegex(ValueError,'IY'):r.step(before,0xa100)
        with self.assertRaisesRegex(ValueError,'A-D only'):body.Rules(b'', 'lair_f')


if __name__=='__main__':unittest.main()
