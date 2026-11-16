#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

import dle_retry_rules as rules


class RetryRulesTest(unittest.TestCase):
    def ram(self):
        ram=bytearray(1024);ram[0x10]=50;ram[0x11]=216;ram[0x31]=3
        ram[0x36]=0x89;ram[0x202]=0x9a
        return ram

    def test_hole_insertion_precedes_older_physical_slots(self):
        ram=self.ram();ram[0xc1]=0x83
        out=rules.append(ram)
        self.assertEqual(list(out[0xc0:0xc3]),[0x9a,0x83,0])
        self.assertEqual(ram[0xc0],0)

    def test_full_queue_and_excluded_hubs(self):
        ram=self.ram();ram[0x202]=0x94
        self.assertEqual(rules.append(ram),ram)
        ram[0xc0:0xc8]=bytes(range(0x81,0x89));ram[0x35]=2
        self.assertEqual(rules.append(ram),ram)

    def test_pending_room_exit_does_not_consume_logical_history(self):
        ram=self.ram();ram[0x35]=32;ram[0x12]=0x8c;ram[0xc0]=0x83
        ram[0x60:0x78]=bytes([7]*24)
        out=rules.dispatch(ram)
        self.assertEqual(out[14:16],bytes([0x83,0]))
        self.assertEqual(out[0x36],ram[0x36])
        self.assertEqual(out[0x60:0x78],ram[0x60:0x78])
        self.assertEqual(out[0xc0],0)

    def test_flush_saves_then_restores_literal_shadow_slot(self):
        ram=self.ram();ram[0x12]=0xa8;ram[0xc0]=0x83;ram[0x205]=255
        out=rules.dispatch(ram)
        self.assertEqual(out[0xd0:0xd2],bytes([0xa8,0x89]))
        self.assertEqual(out[14],0x83)
        self.assertEqual(out[0x205],127)
        done=rules.dispatch(out)
        self.assertEqual(done[14],0xa8)
        self.assertEqual(done[0x86],0x89)
        self.assertEqual(done[0x36],0x89)
        self.assertEqual(done[0x35]&104,8)

    def test_repeated_death_during_replay_does_not_duplicate_room(self):
        ram=self.ram();ram[0x35]=32;ram[0xc1]=0x83
        out=rules.life(ram)
        self.assertEqual(out[0xc0:0xc8],ram[0xc0:0xc8])
        self.assertEqual(out[0x31],2)
        resumed=rules.dispatch(rules.restart(out))
        self.assertEqual(resumed[14:16],bytes([0x83,1]))
        self.assertEqual(resumed[0xc1],0)

    def test_dragon_death_restarts_in_place(self):
        ram=self.ram();ram[0x202]=0xa4;ram[0x205]=4
        out=rules.life(ram)
        self.assertEqual(out[0x30],0xa4)
        self.assertFalse(any(out[0xc0:0xc8]))
        self.assertFalse(out[0x35]&64)
        self.assertEqual(rules.restart(out)[14:16],bytes([0xa4,1]))

    def test_bad_contexts_fail(self):
        with self.assertRaises(ValueError):rules.drain(self.ram())
        with self.assertRaises(ValueError):rules.append(self.ram(),player=0x31)
        ram=self.ram();ram[0x11]=0
        with self.assertRaises(ValueError):rules.life(ram)


if __name__=='__main__':unittest.main()
