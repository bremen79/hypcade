#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify the reduced loop algebra against an independent step interpreter."""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import unittest

from future_roms.rom_phase_classes import LoopClasses


class PhaseClassesTest(unittest.TestCase):
    def test_small_domains_against_step_interpreter(self):
        # The reference explicitly consumes each displaced wait iteration,
        # rather than using the quotient or the closed-form orbit period.
        for tw in range(1, 9):
            for tp in range(1, 12):
                for mp in range(4):
                    for mw in range(1, 4):
                        model = LoopClasses(mp, tp, mw, tw)
                        for phase in range(tw):
                            clock, refresh = phase, 0
                            visited = set()
                            n = 0
                            while (clock, refresh) not in visited:
                                self.assertEqual(model.at(phase, n), (clock, refresh))
                                visited.add((clock, refresh))
                                clock += tp
                                refresh += mp
                                while clock >= tw:
                                    clock -= tw
                                    refresh -= mw
                                refresh %= 8
                                n += 1
                            self.assertEqual((clock, refresh), (phase, 0))
                            self.assertEqual(n, model.state_period)

    def test_known_early_poll_cannot_steer_all_selector_residues(self):
        model = LoopClasses(380, 3072, 7, 64)
        self.assertEqual(model.report(), dict(clock_period=1, state_period=2,
            residue_counts=[2], all_phases_cover_refresh=False, worst_cover_events=None))
        self.assertEqual(model.profile(0)['residues'], [0, 4])

    def test_later_rom_timer_regime_has_short_complete_prefix(self):
        model = LoopClasses(404, 3268, 7, 64)
        self.assertEqual(model.report(), dict(clock_period=16, state_period=128,
            residue_counts=[8], all_phases_cover_refresh=True, worst_cover_events=9))
        for phase in range(64):
            self.assertEqual({model.at(phase, n)[1] for n in range(9)}, set(range(8)))

    def test_odd_poll_without_wait_has_eight_classes(self):
        self.assertEqual(LoopClasses(459, 0, 0, 1).report()['worst_cover_events'], 8)
        self.assertEqual(LoopClasses(440, 0, 0, 1).report()['residue_counts'], [1])

    def test_even_costs_preserve_selector_parity(self):
        model = LoopClasses(296, 2429, 10, 90)
        for phase in range(90):
            self.assertTrue(set(model.profile(phase)['residues']) <= {0, 2, 4, 6})
        self.assertFalse(model.report()['all_phases_cover_refresh'])

    def test_invalid_domains_rejected(self):
        for args in ((-1, 1, 1, 1), (1, -1, 1, 1), (1, 1, -1, 1), (1, 1, 1, 0)):
            with self.assertRaises(ValueError):
                LoopClasses(*args)
        model = LoopClasses(1, 1, 1, 2)
        for phase, count in ((-1, 0), (2, 0), (0, -1)):
            with self.assertRaises(ValueError):
                model.at(phase, count)


if __name__ == '__main__':
    unittest.main()
