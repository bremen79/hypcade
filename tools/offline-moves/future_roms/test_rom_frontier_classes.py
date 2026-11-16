#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Boundary and descriptor-priority regressions for nominal frontier classes."""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import unittest

from future_roms.rom_frontier_classes import regions


def entry(slot, ticks, outcome=8):
    return dict(slot=slot, control=4, header=0x84, selector=1, extra=None,
                delay_ticks=0, windows=[dict(window=0, ticks=ticks, outcome=outcome)])


class FrontierClassesTest(unittest.TestCase):
    def test_footer_256_transition_splits_an_open_input_window(self):
        record = dict(inputs=[entry(0, 200)], trailer=[7, 9, 44, 1, 0, 0, 0])
        rows = regions(record, 'lair_d', (4, 0, 8))
        self.assertEqual([(r['start_tick'], r['end_tick']) for r in rows], [(0, 45), (45, 200)])
        self.assertEqual(rows[1]['poll_m1']-rows[0]['poll_m1'], 3)
        self.assertEqual(rows[1]['poll_cycles']-rows[0]['poll_cycles'], 29)

    def test_earlier_accepted_descriptor_shadows_later_safe_outcome(self):
        record = dict(inputs=[entry(0, 10, 9), entry(1, 20)], trailer=[7, 9, 20, 0, 0, 0, 0])
        rows = regions(record, 'lair_d', (4, 3, 8))
        self.assertEqual([(r['start_tick'], r['end_tick']) for r in rows], [(10, 20)])

    def test_even_poll_and_wait_preserve_parity(self):
        selected = entry(0, 3, 10)
        selected.update(header=0xb4, selector=18, extra=64)
        selected['windows'].append(dict(window=1, ticks=5, outcome=8))
        record = dict(inputs=[selected], trailer=[7, 9, 8, 0, 0, 0, 0])
        rows = regions(record, 'lair_d', (4, 1, 8))
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['wait'])
        self.assertEqual(rows[0]['poll_m1'] % 2, 0)
        self.assertEqual(rows[0]['wait_m1'] % 2, 0)
        self.assertEqual(rows[0]['conditional_classes']['parity']['residue_counts'], [1])


if __name__ == '__main__':
    unittest.main()
