
if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

from future_roms.rom_poll_rules import PollCost,cost,memory


class PollRulesTest(unittest.TestCase):
    def test_literal_us_paths(self):
        # Delay-active, second-window-active and two exhausted windows.
        descriptors=[(1,[12,9,0,0]),(3,[0,0,21,0]),(2,[0]*4)]
        self.assertEqual(cost('lair_d',descriptors,35,effects=0x3f),PollCost(375,3005))
        self.assertEqual(cost('lair_d',[],256),PollCost(245,2051))

    def test_space_ace_footer_low_byte_paths_differ(self):
        self.assertEqual(cost('ace',[],35),PollCost(247,2073))
        self.assertEqual(cost('sae',[],35),PollCost(248,2071))
        self.assertEqual(cost('ace',[],256),cost('sae',[],256))
        self.assertEqual(cost('ace',[],35,effects=1),cost('ace',[],35))
        self.assertEqual(cost('ace',[],35,cutoff=34),cost('ace',[],35))
        with self.assertRaisesRegex(ValueError,'expiry cutoff'):cost('ace',[],35,cutoff=35)

    def test_reordering_descriptors_does_not_change_cost(self):
        descriptors=[(1,[0]*4),(3,[0,0,0,7]),(2,[1,2,3,0])]
        self.assertEqual(cost('lair_a',descriptors),cost('lair_a',list(reversed(descriptors))))

    def test_skip_respects_next_external_event(self):
        unit=cost('lair_f',[(2,[0,0,17,0])],9)
        n,bulk,left=unit.fit(131072)
        self.assertEqual(bulk,unit.repeat(n))
        self.assertEqual(bulk.cycles+left,131072)
        self.assertLess(left,unit.cycles)
        self.assertEqual(unit.repeat(10**20).m1,unit.m1*10**20)
        self.assertEqual(unit.fit(unit.cycles-1)[0],0)

    def test_invalid_transfer_domains_fail(self):
        for kwargs in (dict(footer=0),dict(flags=64),dict(flags=128),dict(effects=64),
                       dict(effects=256),dict(flags=-1)):
            with self.assertRaises(ValueError):memory([],**kwargs)
        for descriptors in ([(True,[0]*4)],[(0,[0]*4)],[(1,[0,0,1,0])],[(3,[0,0,-1,0])]):
            with self.assertRaises(ValueError):memory(descriptors)
        with self.assertRaises(ValueError):cost('unknown',[])
        with self.assertRaises(ValueError):PollCost(248,2080).fit(-1)
        with self.assertRaises(ValueError):PollCost(248,2080).repeat(1.5)


if __name__=='__main__':unittest.main()
