#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

from sae_optimality import check_fresh_episodes, lower_bound, verify_potential


class ProofChecks(unittest.TestCase):
    def test_relaxed_shortcut_lowers_bound(self):
        nodes = list(range(4))
        edges = [(0, 1, 1), (1, 2, 1), (2, 3, 0)]
        bound, potential = lower_bound(nodes, edges, [3])
        self.assertEqual(bound, 2)
        verify_potential(edges, [3], potential, bound)
        # A previously unmodeled free shortcut must invalidate the old proof.
        edges.append((0, 3, 0))
        with self.assertRaises(ValueError):
            verify_potential(edges, [3], potential, bound)
        self.assertEqual(lower_bound(nodes, edges, [3])[0], 0)

    def test_dead_end_and_automatic_trap(self):
        edges = [(0, 1, 0), (1, 2, 1), (0, 3, 0), (3, 3, 0)]
        bound, potential = lower_bound(list(range(4)), edges, [2])
        self.assertEqual(bound, 1)
        verify_potential(edges, [2], potential, bound)

    def test_live_cycle_rejected(self):
        edges = [(0, 1, 0), (1, 0, 0), (1, 2, 1), (0, 3, 0)]
        with self.assertRaisesRegex(ValueError, 'decision DAG required'):
            lower_bound(list(range(4)), edges, [2])

    def test_revisit_across_queue_positions(self):
        states = [(1, 1, 0, 0), (2, 2, 0, 1), (1, 1, 0, 2)]
        with self.assertRaises(ValueError):
            check_fresh_episodes(states, [(0, 1, 0), (1, 2, 0)])

    def test_scheduler_cycle(self):
        states = [(1, 1, 0, 0), (2, 2, 0, 0)]
        with self.assertRaises(ValueError):
            check_fresh_episodes(states, [(0, 1, 0), (1, 0, 0)])

    def test_same_episode_reentry(self):
        with self.assertRaises(ValueError):
            check_fresh_episodes([(1, 1, 1, 0), (1, 1, 0, 0)], [(0, 1, 0)])


if __name__ == '__main__':
    unittest.main()
