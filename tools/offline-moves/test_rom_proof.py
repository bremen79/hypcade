#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
import copy
import unittest
import rom_proof as p


def graph(awards, links, goals):
    return dict(states=list(range(len(awards))), awards=awards, goals=goals, deaths=[],
                actions=[[(label, targets) for source, label, targets in links if source == u] for u in range(len(awards))])


class ProofTest(unittest.TestCase):
    def test_different_future_exits_and_off_policy_state(self):
        g = graph([0, 5, 2, 10, 0], [(0, (1, 0, 1), [1]), (0, (2, 0, 2), [2]),
            (1, (1, 0, 4), [4]), (2, (0, 0, 3), [3]), (3, (1, 0, 4), [4])], [4])
        r = p.solve(g)
        self.assertEqual(r['fewest'], [2, 1, 1, 1, 0])
        self.assertEqual(r['highest_score'], [12, 5, 12, 10, 0])
        ranks, unequal = p.ranked(g, r, 'highest-score')
        self.assertEqual(ranks[0][0][1][0], 2)
        self.assertFalse(unequal)
        damaged = copy.deepcopy(r)
        damaged['highest_score'][0] -= 1
        with self.assertRaises(ValueError):
            p.verify(g, damaged)

    def test_wait_cycle_with_input_exit_is_rejected(self):
        g = graph([0, 0, 5, 0], [(0, (0, 0, 1), [1]), (1, (0, 0, 0), [0]),
            (1, (1, 0, 2), [2]), (3, (0, 0, 3), [3])], [2])
        with self.assertRaisesRegex(ValueError, 'decision DAG required'):
            p.solve(g)

    def test_automatic_trap_and_feeder_have_no_surviving_policy(self):
        g = graph([0, 100, 0, 7], [(0, (0, 0, 1), [1]),
            (1, (0, 0, 2), [2]), (2, (0, 0, 1), [1])], [3])
        r = p.solve(g)
        self.assertEqual(r['fewest'], [None, None, None, 0])
        self.assertEqual(r['highest_score'], [None, None, None, 7])
        self.assertEqual(p.decision_dag(g)['nodes'], [3])

    def test_forced_chain_preserves_rewards_and_deviation_values(self):
        g = graph([2, 10, 20, 1, 4], [(0, (1, 0, 1), [1]),
            (0, (2, 0, 3), [3]), (1, (0, 0, 2), [2]),
            (2, (0, 0, 4), [4]), (3, (1, 0, 4), [4])], [4])
        r = p.solve(g)
        self.assertEqual(r['fewest'], [1, 0, 0, 1, 0])
        self.assertEqual(r['highest_score'], [36, 34, 24, 5, 4])
        dag = p.decision_dag(g)
        self.assertEqual(set(dag['nodes']), {0, 3, 4})
        self.assertEqual(dag['actions'][0][0][1], [(4, 30)])
        self.assertEqual(p.ranked(g, r, 'shortest')[0][0][0][1][0], 1)

    def test_automatic_nature_branch_remains_explicit(self):
        g = graph([2, 3, 9], [(0, (0, 0, 1), [1, 2])], [1, 2])
        self.assertIn(0, p.decision_dag(g)['nodes'])
        r = p.solve(g)
        self.assertEqual(r['highest_score'][0], 11)
        self.assertTrue(p.ranked(g, r, 'highest-score')[1])

    def test_tampered_secondary_potential_rejected(self):
        g = graph([0, 5], [(0, (1, 0, 1), [1])], [1])
        for key in ('score_at_fewest', 'fewest_at_score'):
            r = p.solve(g)
            r[key][0] += 1
            with self.assertRaisesRegex(ValueError, 'Bellman equality'):
                p.verify(g, r)

    def test_long_forced_chain_needs_no_recursion(self):
        count = 2500
        g = dict(states=list(range(count)), awards=[1] * count, goals=[count - 1], deaths=[],
                 actions=[[((0, 0, u + 1), [u + 1])] for u in range(count - 1)] + [[]])
        r = p.solve(g)
        self.assertEqual(r['highest_score'][0], count)
        self.assertEqual(len(p.decision_dag(g)['nodes']), 1)

    def test_positive_reward_cycle_rejected(self):
        g = graph([1, 0], [(0, (1, 0, 0), [0]), (0, (1, 0, 1), [1])], [1])
        with self.assertRaisesRegex(ValueError, 'decision DAG required'):
            p.solve(g)

    def test_nature_not_silently_averaged(self):
        g = graph([0, 5, 10], [(0, (1, 0, 1), [1, 2])], [1, 2])
        r = p.solve(g)
        _, unequal = p.ranked(g, r, 'highest-score')
        self.assertEqual(len(unequal), 1)
        self.assertEqual(r['highest_score'][0], 10)


if __name__ == '__main__':
    unittest.main()
