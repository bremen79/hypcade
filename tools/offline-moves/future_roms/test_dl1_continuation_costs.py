#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the resource join against independent chronological continuation DAGs."""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

from functools import lru_cache
import unittest

from dl1_allocation import add
from future_roms.dl1_continuation_costs import allocate, observations
from test_dl1_allocation import transitions


class ContinuationCostsTest(unittest.TestCase):
    def test_every_prefix_matches_chronological_exhaustive_solution(self):
        groups = [[1, 2, 3], [4, 5, 6]]
        table = transitions()
        # Includes an optional substitution on visit two, leaving one of
        # the ordinary variants unconsumed after all three visits.
        path = [(0, 1), (3, 0), (2, 2)]
        points = []
        masks, used = [0, 0], 0
        for lap in range(3):
            for g in range(2):
                choice = path[lap][g]
                transition = next(t for t, _ in table[used, masks[g]] if t[0] == choice)
                _, masks[g], used = transition
                points.append(((lap, g), dict(scene=groups[g][choice]+40 if choice < 3 else 80,
                    mask=masks[g], used=used)))
        for sign in (1, -1):
            costs = {r: (sign*(r % 7), sign*(-13*r % 19)) for r in range(85)}
            for cut in range(7):
                known = dict(points[:cut])
                @lru_cache(None)
                def chronological(lap, g, history, used):
                    if lap == 3:
                        return (0, 0)
                    options = []
                    for (choice, mask, nxt_used), _ in table[used, history[g]]:
                        root = groups[g][choice]+40 if choice < 3 else 80
                        point = dict(scene=root, mask=mask, used=nxt_used)
                        if (lap, g) in known and known[lap, g] != point:
                            continue
                        h = list(history)
                        h[g] = mask
                        nxt = (g+1) % 2
                        tail = chronological(lap+int(not nxt), nxt, tuple(h), nxt_used)
                        if tail is not None:
                            options.append(add(costs[root], tail))
                    return min(options) if options else None
                result = allocate(groups, table, costs, known, boundaries=(0, 1))
                self.assertEqual(result['value'], chronological(0, 0, (0, 0), 0))

    def test_incompatible_observation_fails(self):
        with self.assertRaisesRegex(ValueError, 'No selector-support allocation'):
            allocate([[1, 2, 3]], transitions(), {r: (1, 0) for r in range(85)},
                {(1, 0): dict(scene=999, mask=1, used=0)}, boundaries=(0, 1))

    def test_first_visit_injection_is_not_assumed_away(self):
        table = transitions()
        table[0, 0].append(((3, 0, 1), 3))
        with self.assertRaisesRegex(ValueError, 'first visit must not inject'):
            allocate([[1, 2, 3]], table, {})

    def fixture(self):
        groups = [list(range(3*g+1, 3*g+4)) for g in range(12)]
        groups[0] = [1, 2, 1]  # Two physical aliases, different history bits.
        final = [20, 30, 36]
        rows = []
        for lap in range(3):
            for g in range(13):
                rows.append(dict(type='late_entry', group=g+1,
                    scene=(groups[g][lap] if g < 12 else final[lap])+40,
                    mask=(1, 3, 7)[lap] if g < 12 else (4, 6, 7)[lap]))
        return groups, final, rows

    def test_alias_history_survives_record_entry_collapse(self):
        groups, final, rows = self.fixture()
        result = observations([r for row in rows for r in (row, dict(row))], groups, final)
        self.assertEqual(len(result), 39)
        self.assertEqual((result[0]['scene'], result[0]['mask']), (41, 1))
        self.assertEqual((result[26]['scene'], result[26]['mask']), (41, 7))

    def test_optional_room_cannot_consume_the_same_flag_twice(self):
        groups, final, rows = self.fixture()
        rows[13+2].update(scene=80, mask=1)
        rows[13+3].update(scene=80, mask=1)
        with self.assertRaisesRegex(ValueError, 'Optional-room resource'):
            observations(rows, groups, final)


if __name__ == '__main__':
    unittest.main()
