#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exit-specific costs must preserve objectives, rewards and unsafe states."""
import unittest

import dl1_exit_strategies as p
import rom_proof
from test_rom_proof import graph


class ExitStrategiesTest(unittest.TestCase):
    def fixture(self):
        return graph([2, 5, 10, 3, 7, 0],
                     [(0, (1, 0, 1), [1]), (0, (2, 0, 2), [2]),
                      (1, (0, 0, 3), [3]), (2, (0, 0, 4), [4]),
                      (5, (1, 0, 4), [4])], [3, 4])

    def test_exit_continuation_changes_tie_and_includes_terminal_award(self):
        g = self.fixture()
        coefficients = p.factor(g, {3: 'a', 4: 'b'})
        future = dict(a=dict(zip(p.FIELDS, (0, 0, 0, 0))),
                      b=dict(zip(p.FIELDS, (9, 20, 100, 12))))
        result = p.evaluate(coefficients, future)
        self.assertEqual((result['fewest'][0], result['score_at_fewest'][0]), (1, 10))
        self.assertEqual((result['highest_score'][0], result['fewest_at_score'][0]), (119, 13))
        self.assertEqual((result['fewest'][5], result['score_at_fewest'][5]), (10, 27))
        self.assertEqual(p.ranked(g, coefficients, future, 'shortest')[1][0][0][1][0], 1)
        self.assertEqual(p.ranked(g, coefficients, future, 'highest-score')[1][0][0][1][0], 2)

    def test_common_exit_is_a_constant_offset_at_every_step(self):
        g = self.fixture()
        coefficients = p.factor(g, {3: 'same', 4: 'same'})
        tail = dict(zip(p.FIELDS, (8, 33, 50, 12)))
        result = p.evaluate(coefficients, {'same': tail})
        original = rom_proof.solve(g)
        for key in p.FIELDS:
            self.assertEqual(result[key], [v+tail[key] for v in original[key]])

    def test_independent_extended_game_checks_both_objectives(self):
        g = self.fixture()
        terminals = {3: 'a', 4: 'b'}
        self.assertEqual(p.check_numeric_tails(g, p.factor(g, terminals), terminals), 24)

    def test_unknown_exit_is_not_silently_free(self):
        coefficients = p.factor(self.fixture(), {3: 'a', 4: 'b'})
        with self.assertRaisesRegex(ValueError, 'explicit continuation'):
            p.evaluate(coefficients, {'a': dict.fromkeys(p.FIELDS, 0)})
        with self.assertRaisesRegex(ValueError, 'explicit exit identity'):
            p.factor(self.fixture(), {3: 'a'})

    def test_unsafe_state_stays_unsafe_despite_future_reward(self):
        g = graph([0, 0, 5], [(0, (1, 0, 1), [1])], [2])
        result = p.evaluate(p.factor(g, {2: 'a'}), {'a': dict.fromkeys(p.FIELDS, 1000)})
        self.assertIsNone(result['fewest'][0])
        self.assertIsNone(result['highest_score'][1])

    def test_explicit_dead_future_removes_only_its_exit(self):
        coefficients = p.factor(self.fixture(), {3: 'a', 4: 'b'})
        future = {'a': dict.fromkeys(p.FIELDS, 0), 'b': dict.fromkeys(p.FIELDS, None)}
        values = p.evaluate(coefficients, future)
        self.assertEqual(values['highest_score'][0], 10)
        self.assertIsNone(values['fewest'][5])
        future['a'] = dict.fromkeys(p.FIELDS, None)
        self.assertTrue(all(v is None for v in p.evaluate(coefficients, future)['fewest']))

    def test_stochastic_local_edges_require_explicit_contract(self):
        g = graph([0, 1, 2], [(0, (1, 0, 0), [1, 2])], [1, 2])
        with self.assertRaisesRegex(ValueError, 'probability contract'):
            p.factor(g, {1: 'a', 2: 'b'})


if __name__ == '__main__':
    unittest.main()
