#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

from late_order_invariance import factor


class FactorTest(unittest.TestCase):
    def table(self):
        return {(0,m):[((i,m|(1<<i),0),0) for i in range(3) if not m&(1<<i)] for m in range(7)}

    def test_remaining_cost_is_sum_of_unconsumed_variants(self):
        costs=((1,10),(3,20),(5,40));answer=factor(self.table(),costs)
        for mask,actual in answer['values'].items():
            expected=tuple(sum(costs[i][j] for i in range(3) if not mask&(1<<i)) for j in range(2))
            self.assertEqual(actual,expected)

    def test_optional_injection_or_repeated_variant_is_rejected(self):
        for alternative in ((3,0,1),(0,0,0),(0,3,0)):
            table=self.table();table[0,0]=[(alternative,0)]
            with self.assertRaisesRegex(ValueError,'fresh-variant'):factor(table,((1,),(2,),(3,)))


if __name__=='__main__':unittest.main()
