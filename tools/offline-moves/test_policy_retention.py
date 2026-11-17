#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Retention tolerance, room-history assumptions and actual packaged coverage."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import policy_retention as r


class RetentionTest(unittest.TestCase):
    def us(self, gap):
        values = {'fewest': [10]*85, 'fewest_at_score': [10]*85}
        values['fewest_at_score'][72] += gap
        table = dict(kind='ArcadeRomRule', certificate=dict(
            graph=dict(states=[[i, 0] for i in range(85)]), values=values))
        descriptors = {str(i): {'scenes': list(range(3*i-2, 3*i+1))} for i in range(1, 13)}
        descriptors['13'] = {'scenes': [37, 38, 39]}
        selectors = [dict(rows=[dict(mask=0, support=[[[0, 1, 0], 0]]),
                                      dict(mask=1, support=[[[1, 3, 0], 0]])])]
        case = dict(game='lair_a', descriptors=descriptors, selector_tables=selectors)
        return table, case

    def decide_us(self, table, case):
        with TemporaryDirectory() as directory:
            root = Path(directory);(root/'proof-inputs').mkdir()
            (root/'proof-inputs/us-selectors.json').write_text(json.dumps({'cases': [case]}))
            with patch.object(r, 'ROOT', root):
                return r.decide('lair_a', table, root)

    def test_one_input_collapses_but_two_inputs_do_not(self):
        for gap, count in ((0, 1), (1, 1), (2, 2)):
            table, case = self.us(gap)
            result = self.decide_us(table, case)
            self.assertEqual(result['max_extra_inputs'], gap)
            self.assertEqual(len(result['objectives']), count)

    def test_repeated_positive_slot_is_counted_twice(self):
        table, case = self.us(1)
        case['descriptors']['1']['scenes'][0] = 32
        self.assertEqual(len(self.decide_us(table, case)['objectives']), 2)

    def test_repeating_history_cannot_certify_the_tolerance(self):
        table, case = self.us(1)
        case['selector_tables'][0]['rows'][0]['mask'] = 1
        with self.assertRaisesRegex(ValueError, 'repeat'):
            self.decide_us(table, case)

    def test_pruning_keeps_all_retained_alternatives_and_remaps_indices(self):
        table = dict(kind='ArcadeRomRule', rules=[[1, 0, 2, 1], [1, 0, 3, 8], [1, 0, 4, 16]],
                     orders={'highest-score': [2, 0], 'shortest': [1, 0]},
                     retention={'objectives': ['highest-score']})
        packed = r.runtime_table(table)
        self.assertEqual(packed['rules'], [table['rules'][0], table['rules'][2]])
        self.assertEqual(packed['orders'], {'highest-score': [1, 0]})
        self.assertEqual(len(table['rules']), 3)
        self.assertIn('shortest', table['orders'])

    def test_generated_ui_follows_retention_instead_of_rom_name(self):
        source = r.java_catalog({'new_rom': {'retention': {'objectives': r.OBJECTIVES}},
                                 'ace': {'retention': {'objectives': ['highest-score']}}})
        self.assertIn('"new_rom".equals(game)', source)
        self.assertNotIn('"ace".equals(game)', source)


if __name__ == '__main__':
    unittest.main()
