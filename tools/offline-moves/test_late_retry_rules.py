#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Original small recovery examples, especially repeated queued-room deaths."""
import unittest

import late_retry_rules as rules


class LateRetryTest(unittest.TestCase):
    def state(self):
        ram=bytearray(1024);ram[16]=38;ram[17]=216;ram[49]=5;ram[54]=13
        return ram

    def test_full_queue_does_not_consume_bonus_or_overwrite(self):
        ram=self.state();ram[53]=2;ram[0x202]=150;ram[0xc0:0xc8]=bytes(range(129,137))
        self.assertEqual(rules.append(ram),ram)
        ram[0xc3]=0;after=rules.append(ram)
        self.assertEqual(after[0xc3],155)
        self.assertEqual(after[53]&2,0)

    def test_multiple_deaths_in_pending_room_reinsert_that_room(self):
        ram=self.state();ram[53]=32;ram[0xc1]=140;ram[0xc3]=150
        ram[0xd0]=206;ram[0xd1]=13;ram[0x202]=155
        for remaining in (4,3,2):
            dead=rules.life(ram)
            self.assertEqual((dead[0xc0],dead[48],dead[49]),(155,155,remaining))
            restarted=rules.restart(dead)
            ram=rules.dispatch(restarted)
            self.assertEqual((ram[14],ram[15],ram[54]),(155,1,13))
            self.assertEqual(list(ram[0xc0:0xc4]),[0,140,0,150])

    def test_empty_drain_restores_dragon_and_literal_shadow(self):
        ram=self.state();ram[53]=32|64|128;ram[0xd0]=206;ram[0xd1]=13
        ram[54]=9
        after=rules.drain(ram)
        self.assertEqual((after[14],after[15],after[54],after[0x60]),(206,1,9,13))
        self.assertEqual(after[53],12)

    def test_immediate_restart_does_not_enqueue_or_advance(self):
        ram=self.state();ram[0x205]=4;ram[0x202]=206
        dead=rules.life(ram);after=rules.restart(dead)
        self.assertEqual(list(after[0xc0:0xc8]),[0]*8)
        self.assertEqual((after[14],after[15]),(206,1))

    def test_dispatch_flushes_only_at_original_dragon_boundaries(self):
        for root in (164,206):
            ram=self.state();ram[18]=root;ram[0xc2]=145
            after=rules.dispatch(ram)
            self.assertEqual((after[0xd0],after[0xd1],after[14]),(root,13,145))
            self.assertEqual(after[53]&32,32)
        ram=self.state();ram[18]=163
        self.assertEqual(rules.dispatch(ram),ram)

    def test_explicit_intermission_exit_ignores_overwritten_episode(self):
        ram=self.state();ram[54]=62;ram[18]=129;ram[0x205]=2
        self.assertEqual(rules.advance(ram),ram)
        ram[0x205]=0
        self.assertEqual(rules.advance(ram)[18],191)


if __name__=='__main__':unittest.main()
