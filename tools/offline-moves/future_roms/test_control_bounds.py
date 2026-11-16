
if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from future_roms.control_bounds import audit, audit_fewest_tolerance
from test_rom_proof import graph


class ControlBoundsTest(unittest.TestCase):
    def test_tolerance_is_one_total_input_not_one_per_decision(self):
        g=graph([0]*5,[(0,(0,0,0),[1]),(0,(1,0,0),[2]),
                       (2,(0,0,0),[1]),(1,(0,0,0),[4]),
                       (1,(1,0,0),[3]),(3,(0,0,0),[4])],[4])
        rows=audit_fewest_tolerance(g,[1,1,0,0,None])
        self.assertEqual(rows[0]['expected_regret_upper_bound'],2)
        self.assertFalse(rows[0]['certified'])
        self.assertTrue(rows[1]['certified'])

    def test_tolerance_bounds_unknown_action_dependent_probabilities(self):
        g=graph([0]*4,[(0,(1,0,0),[1,2]),(2,(1,0,0),[3])],[1,3])
        row=audit_fewest_tolerance(g,[0,None,0,None])[0]
        self.assertEqual(row['moves'],dict(min=1,max=2))
        self.assertEqual(row['expected_regret_upper_bound'],1)
        self.assertTrue(row['certified'])
        self.assertFalse(audit_fewest_tolerance(g,[0,None,0,None],0)[0]['certified'])

    def test_tolerance_does_not_accept_a_policy_with_a_dead_branch(self):
        g=graph([0]*3,[(0,(1,0,0),[1,2])],[1])
        self.assertIsNone(audit_fewest_tolerance(g,[0,None,None])[0])

    def test_unequal_values_but_control_is_proved(self):
        g = graph([0, 10, 12, 3], [(0, (1, 0, 0), [1, 2]),
                                   (0, (2, 0, 0), [3])], [1, 2, 3])
        for objective in ('shortest', 'highest-score'):
            row = audit(g, [0, None, None, None], objective)[0]
            self.assertTrue(row['certified'])
            self.assertNotEqual(row['low'], row['high'])
            self.assertEqual(row['moves'], dict(min=1, max=1))
            self.assertEqual(row['score'], dict(min=10, max=12))

    def test_same_conditional_ranking_is_insufficient(self):
        # A beats B in each paired outcome: 10>9 and 2>1. An
        # action-dependent law can nevertheless favor B (9) over A (2).
        g = graph([0, 10, 2, 9, 1], [(0, (1, 0, 0), [1, 2]),
                                      (0, (2, 0, 0), [3, 4])], [1, 2, 3, 4])
        for objective in ('shortest', 'highest-score'):
            self.assertFalse(audit(g, [0, None, None, None, None], objective)[0]['certified'])

    def test_downstream_uncertainty_is_not_hidden(self):
        g = graph([0, 0, 10, 2, 9, 1], [(0, (0, 0, 0), [1]),
                    (1, (1, 0, 0), [2, 3]), (1, (2, 0, 0), [4, 5])], [2, 3, 4, 5])
        rows = audit(g, [0, 0, None, None, None, None])
        self.assertTrue(rows[0]['local'])
        self.assertFalse(rows[0]['certified'])

    def test_unsafe_competitor_is_excluded(self):
        g = graph([0, 10, 999], [(0, (1, 0, 0), [1]),
                                  (0, (2, 0, 0), [2])], [1])
        self.assertTrue(audit(g, [0, None, None])[0]['certified'])


if __name__ == '__main__':
    unittest.main()
