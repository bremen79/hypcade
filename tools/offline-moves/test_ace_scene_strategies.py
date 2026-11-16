#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

from ace_scene_strategies import block
from scene_strategies import solve_scenes, part_for
import rom_proof


class AceCompositionTest(unittest.TestCase):
    def test_replay_exit_has_its_own_cost_and_retains_checkpoint(self):
        graph=dict(states=[(1,10,0,0,0,1,0),(1,10,1,0,0,3,0),
                           (1,11,0,0,1,1,0),(2,12,0,1,0,1,0)],
                   actions=[[((4,0,1),[1]),((8,3,0),[2])],[((0,0,128),[3])],
                            [((1,0,128),[3])],[]],
                   awards=[3,5,100,17],goals=[3],deaths=[])
        values,paths,count=solve_scenes(graph,key=block)
        self.assertEqual(count,3)
        self.assertEqual(values,rom_proof.solve(graph))
        self.assertEqual(values['fewest'][0],1)
        self.assertEqual(values['highest_score'][0],120)
        part=part_for(graph,paths,values,'highest-score',0,(8,3,0),2,key=block)
        self.assertEqual(part['local_inputs'],1)
        self.assertEqual(part['exit_inputs'],1)
        self.assertEqual(part['remaining_inputs'],2)
        self.assertEqual(part['remaining_score'],120)
        self.assertEqual(block(graph['states'][0]),block(graph['states'][1]))
        self.assertNotEqual(block(graph['states'][0]),block(graph['states'][2]))


if __name__=='__main__':unittest.main()
