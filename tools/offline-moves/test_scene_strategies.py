#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent small games checking exit costs and local/global composition."""
import unittest
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import rom_tables
from verify_cost_runtime import verify_saved_values
from scene_strategies import solve_scenes
from test_sae_continuations import game


class ExitCostTest(unittest.TestCase):
    def graph(self):
        return dict(states=list(range(5)), awards=[0, 586, 586, 0, 0], goals=[3, 4],
                    actions=[[((4, 0, 1), [1]), ((8, 3, 2), [2])],
                             [((0, 0, 3), [3])], [((0, 0, 4), [4])], [], []])

    def exits(self):
        return {3: dict(fewest=10, score_at_fewest=100, highest_score=200, fewest_at_score=12),
                4: dict(fewest=8, score_at_fewest=100, highest_score=250, fewest_at_score=13)}

    def test_exit_cost_breaks_locally_equal_choices(self):
        values, paths = rom_tables.solve_scene(self.graph(), [0, 1, 2], self.exits())
        self.assertEqual(values['fewest'][0], 9)
        self.assertEqual(values['score_at_fewest'][0], 686)
        self.assertEqual(paths['shortest'][0], dict(local_inputs=1, local_score=586,
                                                  exit=4, exit_inputs=8, exit_score=100))
        self.assertEqual(values['highest_score'][0], 836)
        self.assertEqual(values['fewest_at_score'][0], 14)

    def test_uses_selected_objectives_continuation(self):
        exits = self.exits()
        exits[3]['highest_score'] = 1000
        values, paths = rom_tables.solve_scene(self.graph(), [0, 1, 2], exits)
        self.assertEqual(values['fewest'][0], 9)
        self.assertEqual(values['highest_score'][0], 1586)
        self.assertEqual(paths['highest-score'][0]['exit'], 3)
        self.assertEqual(values['fewest_at_score'][0], 13)

    def test_unknown_exit_is_not_silently_free(self):
        with self.assertRaisesRegex(ValueError, 'no continuation value'):
            rom_tables.solve_scene(self.graph(), [0, 1, 2], {})

    def test_resolved_dead_exit_is_not_a_winning_option(self):
        exits = self.exits()
        exits[4] = {k: None for k in exits[4]}
        values, _ = rom_tables.solve_scene(self.graph(), [0, 1, 2], exits)
        self.assertEqual(values['fewest'][0], 11)
        self.assertIsNone(values['fewest'][2])

    def test_local_cycle_fails_closed(self):
        graph = self.graph()
        graph['actions'][1] = [((0, 0, 0), [0])]
        with self.assertRaisesRegex(ValueError, 'not a DAG'):
            rom_tables.solve_scene(graph, [0, 1, 2], self.exits())

    def test_score_suppression_and_retry_values_survive_composition(self):
        solution = game()
        for graph, expected in zip(solution.graphs, solution.values):
            actual, paths, _ = solve_scenes(graph)
            self.assertEqual(actual, expected)
            for objective, parts in paths.items():
                for u, part in enumerate(parts):
                    if part is None:
                        continue
                    a, b, _, c, d = part
                    self.assertEqual(a+c, actual['fewest' if objective == 'shortest' else 'fewest_at_score'][u])
                    self.assertEqual(b+d, actual['score_at_fewest' if objective == 'shortest' else 'highest_score'][u])


class SavedExitCostTest(unittest.TestCase):
    def write_case(self, folder, local=1, solved=9):
        part = dict(local_inputs=local, exit_inputs=8, remaining_inputs=9,
                    local_score=586, exit_score=100, remaining_score=686)
        row = dict(phases=[dict(values=dict(fewest=solved, score_at_fewest=686),
            policies={'shortest': [dict(rank=0, branches=[part])]})])
        path = folder / 'cadet-d0-values.jsonl'
        path.write_text('{}\n' + json.dumps(row) + '\n')
        manifest = dict(runtime_timing='live-rom', cases=[dict(skill='cadet', difficulty=0, states=1)],
                        files={path.name: hashlib.sha256(path.read_bytes()).hexdigest()})
        (folder / 'manifest.json').write_text(json.dumps(manifest))

    def test_saved_components_and_selected_value(self):
        with TemporaryDirectory() as name:
            folder = Path(name)
            self.write_case(folder)
            self.assertEqual(verify_saved_values(folder)['branch_decompositions'], 1)
            self.write_case(folder, local=2)
            with self.assertRaisesRegex(ValueError, 'does not add up'):
                verify_saved_values(folder)
            self.write_case(folder, solved=10)
            with self.assertRaisesRegex(ValueError, 'differs from solved value'):
                verify_saved_values(folder)

    def test_modified_saved_file_is_rejected(self):
        with TemporaryDirectory() as name:
            folder = Path(name)
            self.write_case(folder)
            with (folder / 'cadet-d0-values.jsonl').open('a') as stream:
                stream.write('{}\n')
            with self.assertRaisesRegex(ValueError, 'checksum differs'):
                verify_saved_values(folder)


if __name__ == '__main__':
    unittest.main()
