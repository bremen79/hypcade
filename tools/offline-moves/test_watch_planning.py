#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Count effective packaged policies, not equivalent selection values."""
import unittest
from verify_watch_moves import unique_modes


class PlanningTest(unittest.TestCase):
    def test_single_policy_runs_once(self):
        self.assertEqual(unique_modes([1, 2], True), [1])
        self.assertEqual(unique_modes([0, 1, 2], True), [1])

    def test_distinct_policies_are_both_retained(self):
        self.assertEqual(unique_modes([0, 1, 2], False), [1, 2])
        self.assertEqual(unique_modes([1, 2], False), [1, 2])

    def test_explicit_off_or_alias_remains_testable(self):
        self.assertEqual(unique_modes([0], True), [0])
        self.assertEqual(unique_modes([2], True), [2])


if __name__ == '__main__':
    unittest.main()
