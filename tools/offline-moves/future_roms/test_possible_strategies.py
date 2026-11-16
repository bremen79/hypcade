
if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from test_rom_proof import graph
from future_roms.possible_strategies import solve


class PossibleStrategiesTest(unittest.TestCase):
    def test_minimum_possible_inputs_wins_over_a_better_guarantee(self):
        g=graph([0]*6,[(0,(1,0,0),[1,2]),(0,(2,0,0),[3]),
            (2,(1,0,0),[4]),(4,(1,0,0),[5]),(3,(1,0,0),[1])],[1,5])
        row=solve(g,objective='shortest')['states'][0]
        self.assertEqual(row['action'],0)
        self.assertEqual(row['best_moves'],1)
        self.assertEqual(row['moves'],dict(min=1,max=3))
        self.assertEqual(row['best_targets'],[1])

    def test_shortest_tie_score_belongs_to_the_same_attaining_trajectory(self):
        g=graph([0,10,0,1000],[(0,(1,0,0),[1,2]),(2,(1,0,0),[3])],[1,3])
        row=solve(g,objective='shortest')['states'][0]
        self.assertEqual((row['best_moves'],row['score_at_best_moves']),(1,10))
        self.assertEqual(row['score'],dict(min=10,max=1000))

    def test_shortest_reoptimizes_every_unlucky_or_off_policy_state(self):
        g=graph([0]*5,[(0,(1,0,0),[1,2]),(2,(1,0,0),[3]),
            (2,(2,0,0),[4]),(4,(1,0,0),[3])],[1,3])
        rows=solve(g,objective='shortest')['states']
        self.assertEqual(rows[2]['action'],0)
        self.assertEqual(rows[0]['moves'],dict(min=1,max=2))

    def test_shortest_does_not_deliberately_risk_a_dead_branch(self):
        g=graph([0]*5,[(0,(1,0,0),[1,2]),(0,(2,0,0),[3]),(3,(1,0,0),[4])],[1,4])
        self.assertEqual(solve(g,objective='shortest')['states'][0]['action'],1)

    def test_invalid_objective_rejected(self):
        with self.assertRaisesRegex(ValueError,'objective'):solve(graph([0],[],[0]),objective='expected')

    def test_preferred_policy_only_breaks_equal_attaining_values(self):
        g=graph([0,10,10],[(0,(1,0,0),[1]),(0,(2,0,0),[2])],[1,2])
        self.assertEqual(solve(g,[1,None,None],objective='shortest')['states'][0]['action'],1)
        g['awards'][2]=9
        self.assertEqual(solve(g,[1,None,None],objective='shortest')['states'][0]['action'],0)

    def test_missing_context_preference_fails_instead_of_truncating(self):
        with self.assertRaisesRegex(ValueError,'per state'):
            solve(graph([0,0],[(0,(1,0,0),[1])],[1]),[0],objective='shortest')

    def test_best_possible_wins_over_certainty(self):
        g=graph([0,100,1,99],[(0,(1,0,0),[1,2]),(0,(2,0,0),[3])],[1,2,3])
        r=solve(g)['states'][0]
        self.assertEqual(r['action'],0)
        self.assertEqual(r['best_score'],100)
        self.assertEqual(r['score'],dict(min=1,max=100))
        self.assertEqual(r['best_targets'],[1])

    def test_recovery_continuation_is_available_after_unlucky_branch(self):
        g=graph([0,100,1,2,3],[(0,(1,0,0),[1,2]),
            (2,(1,0,0),[3]),(2,(2,0,0),[4])],[1,3,4])
        rows=solve(g)['states']
        self.assertEqual(rows[2]['action'],1)
        self.assertEqual(rows[0]['score'],dict(min=4,max=100))
        self.assertEqual(rows[0]['moves'],dict(min=1,max=2))

    def test_tie_break_uses_inputs_on_best_score_trajectory(self):
        g=graph([0,10,0,10],[(0,(1,0,0),[1]),(0,(2,0,0),[2]),
                              (2,(1,0,0),[3])],[1,3])
        self.assertEqual(solve(g)['states'][0]['action'],0)

    def test_no_deliberately_unsafe_action(self):
        g=graph([0,100,0,9],[(0,(1,0,0),[1,2]),(0,(2,0,0),[3])],[1,3])
        self.assertEqual(solve(g)['states'][0]['action'],1)


if __name__=='__main__':unittest.main()
