#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Boundary and composition tests for the verified countdown summary."""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import unittest

from future_roms.rom_timer_rules import TimerRule


class TimerRuleTest(unittest.TestCase):
    def setUp(self):
        self.rule=TimerRule(46,42,(-21,-14,-6,2),-3)

    def test_crossing_two_window_boundaries_and_footer_expiry(self):
        # Two delay ticks and three window-zero ticks: 5*88 - 2*21 -
        # 3*14 - 4*3 = 344 M1 fetches. Later windows must remain intact.
        after,footer,delta=self.rule.delta([[2,3,4,0]],4,5)
        self.assertEqual((after,footer,delta),([[0,0,4,0]],0,344%128))

    def test_zero_footer_uses_clamp_path_instead_of_wrapping(self):
        self.assertEqual(self.rule.delta([],1,2),([],0,(43+46)%128))
        self.assertEqual(self.rule.delta([],0,2),([],0,92))

    def test_bulk_and_split_execution_have_identical_state_and_refresh(self):
        original=[[255,0,2,3],[0,17,0,7],[1,1,1,1]]
        for first,second in ((0,42),(1,1),(17,255),(255,65535),(10**12,17)):
            middle,footer,a=self.rule.delta(original,257,first)
            after,last,b=self.rule.delta(middle,footer,second)
            whole,end,total=self.rule.delta(original,257,first+second)
            self.assertEqual((after,last),(whole,end))
            self.assertEqual((a+b)%128,total)

    def test_long_zero_tail_takes_constant_storage_and_keeps_all_timers_zero(self):
        ticks=10**20
        self.assertEqual(self.rule.delta([[1,0,0,0]],0,ticks),([[0,0,0,0]],0,(88*ticks-21)%128))

    def test_malformed_and_negative_states_fail_closed(self):
        for rows,footer,ticks in (([[1,2,3]],0,1),([[256,0,0,0]],0,1),([],65536,1),([],0,-1),([],0,True)):
            with self.assertRaises(ValueError):self.rule.delta(rows,footer,ticks)
        with self.assertRaises(ValueError):TimerRule(46,42,(1,2,3),-3)


if __name__=='__main__':unittest.main()
