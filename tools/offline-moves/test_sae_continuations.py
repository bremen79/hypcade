#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic games testing deviation/retry choices and elapsed windows."""
from dataclasses import replace
from types import SimpleNamespace
import unittest

from rom_rules import InputWindow, Origin
from sae_rules import Record, SaeRules
from sae_continuations import Continuations, input_regions
from test_sae_rules import fixture


def game():
    rules = SaeRules(fixture())
    origin = Origin(0, 'Original synthetic input fixture')
    windows = (InputWindow(0, 0, 4, 61, 0, 20, 0x84, None, origin),
               InputWindow(1, 0, 8, 62, 5, 10, 0x98, 128, origin))
    def record(step, award, flags, default, inputs=()):
        return Record(25, step, 0, 0, award, flags, default, 20, 0, 0, (), inputs)
    rules._records.update({(25, 60): record(60, 0, 0, 59, windows),
                           (25, 61): record(61, 246, 1, 63),
                           (25, 62): record(62, 246, 1, 63),
                           (25, 63): record(63, 0, 32, 0),
                           (25, 59): record(59, 0, 16, 58)})
    mem = rules.configured_memory()
    rules.initial_queue(mem)
    mem.write(0xA036, 158)
    mem.write(0xA00E, 153)
    mem.write(0xA00F, 60)
    mem.write(0xA037, 60)
    rules.new_game = lambda: bytes(mem.ram)
    return Continuations(rules)


class ContinuationTest(unittest.TestCase):
    def test_score_suppression_changes_best_retry_move(self):
        solution = game()
        initial = solution.model.start()
        retry = replace(initial, score_suppressed=True)
        for objective in ('shortest', 'highest-score'):
            self.assertEqual(solution.lookup(initial, objective)['actions'][0]['label'], (4, 0, 61))
            self.assertEqual(solution.lookup(retry, objective)['actions'][0]['label'], (8, 3, 62))
        self.assertEqual(solution.values[0]['highest_score'][solution.index[retry]], 246)

    def test_expired_best_window_uses_best_remaining_continuation(self):
        solution = game()
        retry = replace(solution.model.start(), score_suppressed=True)
        ram = bytearray(solution.model.materialize(retry))
        ram[0xED] = 20  # LEFT still open; RIGHT has elapsed.
        ram[0x20E] = 20
        run = SimpleNamespace(_selected=None, _pending=None, _point=retry,
                              state=lambda: SimpleNamespace(ram=bytes(ram), lives=4))
        result = solution.lookup_live(run, 'highest-score')
        self.assertTrue(result['ready'])
        self.assertEqual(result['actions'][0]['label'], (4, 0, 61))
        self.assertEqual(result['actions'][0]['conditional'][0]['value'], (0, 1))

    def test_awaits_an_already_accepted_move(self):
        solution = game()
        result = solution.lookup_live(SimpleNamespace(_selected=object(), _pending=None), 'shortest')
        self.assertEqual(result['status'], 'await-accepted-transition')
        self.assertEqual(result['actions'], [])

    def test_death_has_recovery_relation_not_reward_optimizing_action(self):
        solution = game()
        point = next(p for p in solution.graph['states'] if p.step == 59)
        result = solution.lookup(point, 'highest-score')
        self.assertEqual(result['status'], 'await-restart')
        self.assertEqual(result['actions'], [])
        self.assertTrue(all(solution.graph['states'][u].score_suppressed for u in result['recovery_targets']))

    def test_unknown_context_is_not_repaired_from_sampled_routes(self):
        solution = game()
        with self.assertRaisesRegex(ValueError, 'Unrecognized ROM context'):
            solution.lookup(replace(solution.model.start(), step=57), 'shortest')

    def test_noninteractive_death_clip_waits_for_actual_restart(self):
        solution = game()
        solution.model.rules._records[25, 58] = replace(solution.model.rules.record(25, 63), step=58)
        point = replace(solution.model.start(), step=58, score_suppressed=True)
        ram = bytearray(1024)
        ram[0x35] = 128
        run = SimpleNamespace(_selected=None, _pending=None, _point=point,
                              state=lambda: SimpleNamespace(ram=bytes(ram), lives=4))
        self.assertEqual(solution.lookup_live(run, 'highest-score')['status'], 'await-restart')

    def test_last_life_has_no_fictitious_restart_strategy(self):
        solution = game()
        run = SimpleNamespace(_selected=None, _pending=None, _point=solution.model.start(),
                              state=lambda: SimpleNamespace(ram=bytes(1024), lives=0))
        self.assertEqual(solution.lookup_live(run, 'shortest')['status'], 'game-over')

    def test_descriptor_order_shadows_later_window_until_first_closes(self):
        solution = game()
        record = solution.model.rules.record(25, 60)
        later = replace(record.windows[1], control=4, start_tick=5, end_tick=30)
        record = replace(record, duration=30, windows=(record.windows[0], later))
        regions = [r for r in input_regions(record) if r['label'] == later.label]
        self.assertEqual(regions, [dict(label=later.label, start=20, end=30)])


if __name__ == '__main__':
    unittest.main()
