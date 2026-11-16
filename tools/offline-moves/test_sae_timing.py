#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic timing-schedule and branch-separation checks; no ROM or compiler."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from sae_timing import TimedAction
from verify_sae_timing import read_trace, timing_frontiers


class ScheduleTest(unittest.TestCase):
    def test_physical_schedule_rejects_invalid_cycles_and_control(self):
        for args in ((16, 10, 9, 20), (16, -1, 9, 20), (17, 0, 1, 2),
                     (16, 0.5, 1, 2), (16, 0, 2, 1), (True, 0, 1, 2),
                     (16, 0, 1, 2**64)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                TimedAction(*args)

    def parse(self, text):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'schedule.trace'
            path.write_text(text)
            return read_trace(path)

    def test_schedule_preserves_absolute_times_and_machine_chain(self):
        a, b = 'a' * 32, 'b' * 32
        trace = self.parse('HYPCADE_ROUTE_V2 %s %s 1 500 1\n16 100 200 300 %s %s 0\n' % (a, b, a, b))
        self.assertEqual(trace['steps'], [(TimedAction(16, 100, 200, 300), a, b)])

    def test_schedule_rejects_broken_chain_or_incomplete_records(self):
        a, b = 'a' * 32, 'b' * 32
        good = 'HYPCADE_ROUTE_V2 %s %s 1 500 1\n16 100 200 300 %s %s 0\n' % (a, b, a, b)
        for text in ('', good.replace(' 1 500', ' 2 500'),
                     good.replace('300 ' + a, '300 ' + b),
                     good.replace(' 0\n', '\n'), good.replace(b, 'invalid')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.parse(text)


class SeparationTest(unittest.TestCase):
    def graph(self):
        # One physical input, then two automatic records, then a refresh read.
        return dict(states=[SimpleNamespace(scene=10, step=i) for i in range(5)],
                    actions=[[((16, 0, 1), [1])], [((0, 0, 2), [2])],
                             [((0, 0, 3), [3, 4])], [], []])

    def values(self):
        return dict(fewest=[1, 0, 0, 0, 0], score_at_fewest=[100]*5,
                    highest_score=[100]*5, fewest_at_score=[1, 0, 0, 0, 0])

    def test_equal_future_values_need_no_timing_search(self):
        for objective in ('shortest', 'highest-score'):
            self.assertEqual(timing_frontiers(self.graph(), self.values(), objective),
                             dict(unequal_branch_actions=0, last_input_records=[]))

    def test_propagates_unequal_reward_to_last_physical_input(self):
        values = self.values()
        values['highest_score'][4] = 99
        self.assertEqual(timing_frontiers(self.graph(), values, 'highest-score'),
                         dict(unequal_branch_actions=1, last_input_records=[(10, 0, 16)]))
        self.assertEqual(timing_frontiers(self.graph(), values, 'shortest')['last_input_records'], [])

    def test_respects_secondary_score_objective(self):
        values = self.values()
        values['score_at_fewest'][4] = 99
        self.assertEqual(timing_frontiers(self.graph(), values, 'shortest')['last_input_records'], [(10, 0, 16)])

    def test_does_not_probe_unsupported_physical_controls(self):
        graph, values = self.graph(), self.values()
        graph['actions'][0] = [((-1, 0, 1), [1])]
        values['highest_score'][4] = 99
        self.assertEqual(timing_frontiers(graph, values, 'highest-score')['last_input_records'], [])


if __name__ == '__main__':
    unittest.main()
