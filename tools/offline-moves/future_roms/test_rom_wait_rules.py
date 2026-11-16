
if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

from future_roms.rom_wait_rules import waits_for_descriptor, windows


class WaitRuleTest(unittest.TestCase):
    def test_outcome_index_not_window_number_selects_the_extra_flag(self):
        entry=dict(header=0xf4,extra=64,selector=3|(1<<2)|(1<<6))
        self.assertTrue(waits_for_descriptor(entry,0))
        self.assertFalse(waits_for_descriptor(entry,1))
        self.assertTrue(waits_for_descriptor(entry,2))

    def test_unflagged_input_cannot_wait_even_with_a_matching_extra_bit(self):
        self.assertFalse(waits_for_descriptor(dict(header=0xe4,extra=255,selector=1),0))
        with self.assertRaises(ValueError):
            waits_for_descriptor(dict(header=0xf4,extra=None,selector=1),0)

    def test_wait_classification_preserves_later_windows_and_excludes_ignored(self):
        entry=dict(header=0xf4,extra=64,selector=3|(1<<4),slot=0,control=4,
                   windows=[dict(window=0,outcome=255,ticks=2),dict(window=1,outcome=8,ticks=21),
                            dict(window=2,outcome=9,ticks=4)])
        result=windows(dict(inputs=[entry]))
        self.assertEqual(len(result),2)
        self.assertEqual(result[0]['outcome'],8)
        self.assertTrue(result[0]['wait_until_descriptor_exhausted'])
        self.assertEqual(result[0]['following_window_ticks'],[4])
        self.assertEqual(result[0]['active_loop_parity'],0)
        self.assertFalse(result[1]['wait_until_descriptor_exhausted'])


if __name__=='__main__':unittest.main()
