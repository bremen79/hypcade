
if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

from future_roms.rom_irq_rules import Rules,State,Transfer


def filtered():
    value=object.__new__(Rules);value.filtered=True;return value


class IRQRulesTest(unittest.TestCase):
    def test_three_literal_filter_paths(self):
        r=filtered()
        self.assertEqual(r.advance(State(3,2),1),Transfer(State(4,2),1,15,145))
        self.assertEqual(r.advance(State(27,2),1),Transfer(State(0,3),0,23,204))
        self.assertEqual(r.advance(State(27,4),1),Transfer(State(0,0),1,23,212))

    def test_full_period_and_large_closed_form(self):
        r=filtered()
        self.assertEqual(r.advance(State(),140),Transfer(State(),136,2140%128,20603))
        n=140*10**20
        after=r.advance(State(),n)
        self.assertEqual(after.state,State())
        self.assertEqual(after.core_calls,136*10**20)
        self.assertEqual(after.cycles,20603*10**20)

    def test_composition_and_skipped_irq_parity(self):
        r=filtered()
        for c in range(28):
            for d in range(5):
                before=State(c,d);a=r.advance(before,57);b=r.advance(a.state,119);whole=r.advance(before,176)
                self.assertEqual((b.state,a.core_calls+b.core_calls,(a.refresh+b.refresh)%128,a.cycles+b.cycles),
                                 (whole.state,whole.core_calls,whole.refresh,whole.cycles))
                self.assertEqual((176-whole.core_calls)&1,(whole.state.fifth-before.fifth)&1)
                self.assertEqual(whole.refresh,(125*176+r.refresh_potential(before)-r.refresh_potential(whole.state))%128)

    def test_invalid_parameters_and_plain_vector(self):
        r=filtered()
        with self.assertRaises(ValueError):State(28,0)
        with self.assertRaises(ValueError):State(0,5)
        with self.assertRaises(ValueError):r.advance(State(),-1)
        r.filtered=False
        self.assertEqual(r.advance(State(),7),Transfer(State(),7,21,231))

    def test_prefix_potential_eliminates_irq_count(self):
        r=filtered()
        for c in range(28):
            for d in range(5):
                before=State(c,d)
                for count in (0,1,27,28,139,140,176,10**20):
                    transfer=r.advance(before,count)
                    a=r.core_potential(before);b=r.core_potential(transfer.state)
                    self.assertEqual((136*transfer.refresh-2140*transfer.core_calls-a[0]+b[0])%(136*128),0)
                    self.assertEqual(136*transfer.cycles,20603*transfer.core_calls+a[1]-b[1])
        r.filtered=False
        self.assertEqual(r.core_potential(State()),(0,0))


if __name__=='__main__':unittest.main()
