#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare prefix conditioning with chronological exhaustive resource games."""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

from functools import lru_cache
import unittest

from dl1_allocation import add, allocate_three
from future_roms.dl1_prefix_costs import condition
from test_dl1_allocation import transitions


class PrefixCostTest(unittest.TestCase):
    def test_conditioned_join_matches_chronological_game(self):
        groups = [[1, 2, 3], [4, 5, 6]]
        table = transitions()
        costs = {r: (r % 7, -(13*r) % 19) for r in range(85)}
        for normal in (0, 1, 2):
            for a in range(3):
                for b in range(3):
                    prefix = [groups[0][a]+(0 if normal else 40),
                              groups[1][b]+(0 if normal == 2 else 40)]
                    first = condition([table, table], prefix, groups, normal, 40)
                    @lru_cache(None)
                    def solve(visit, group, masks, used):
                        if visit == 3:
                            return (0, 0)
                        options = []
                        for (choice, mask, nxt_used), _ in table[used, masks[group]]:
                            root = 80+choice-3 if choice >= 3 else groups[group][choice]+(
                                0 if visit == 0 and group < normal else 40)
                            if visit == 0 and root != prefix[group]:
                                continue
                            following = list(masks)
                            following[group] = mask
                            nxt = (group+1) % 2
                            options.append(add(costs[root], solve(visit+int(not nxt), nxt,
                                tuple(following), nxt_used)))
                        return min(options)
                    result = allocate_three(groups, first, table, costs, normal)
                    self.assertEqual(result['value'], solve(0, 0, (0, 0), 0))

    def test_shared_selector_table_is_not_modified(self):
        table = transitions()
        before = {key: list(rows) for key, rows in table.items()}
        condition([table, table], [41], [[1, 2, 3], [4, 5, 6]], 0, 40)
        self.assertEqual(table, before)

    def test_impossible_version_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'no original selector support'):
            condition([transitions()], [1], [[1, 2, 3]], 0, 40)

    def test_aliased_physical_root_retains_actual_history_bit(self):
        table = transitions()
        roots_only = condition([table], [41], [[1, 2, 1]], 0, 40)
        observed = condition([table], [41], [[1, 2, 1]], 0, 40, [4])
        self.assertEqual({r[0][0] for r in roots_only[0][0, 0]}, {0, 2})
        self.assertEqual({r[0][0] for r in observed[0][0, 0]}, {2})


if __name__ == '__main__':
    unittest.main()
