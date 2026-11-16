#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

from late_progression_rules import initialize,resume_selector,verify_itinerary


class ProgressionTest(unittest.TestCase):
    def test_initialization_clears_history_queue_and_score(self):
        ram=bytearray([37]*1024);ram[16]=54;ram[24]=128;ram[21]=197
        out=initialize(ram)
        self.assertEqual(list(out[48:56]),[128,197,0,0,0,0,0,0])
        self.assertEqual(out[0x60:0x90],bytes(48));self.assertEqual(out[0xc0:0xc8],bytes(8))
        self.assertEqual(out[0x90:0xc0],ram[0x90:0xc0])
        self.assertEqual(out[9],37)
        ram[16]=38;self.assertEqual(initialize(ram)[9],36)

    def test_immediate_resume_overwrites_episode_but_not_history(self):
        ram=bytearray(1024);ram[16]=54;ram[18]=206;ram[53]=128;ram[54]=13
        ram[0x61:0x6e]=bytes([7]*13)
        out=resume_selector(ram,0x30)
        self.assertEqual((out[54],out[0x54]),(78,78))
        self.assertEqual(out[0x61:0x6e],ram[0x61:0x6e])
        ram[53]=32;self.assertEqual(resume_selector(ram,0x30),ram)

    def groups(self):
        result={g:(3*g,3*g+1,3*g+2) for g in range(1,13)}
        result[13]=(78,72,62)
        return result

    def test_history_staircase_on_each_pass(self):
        groups=self.groups()
        for lap,final in ((1,0),(2,4),(3,6)):
            for group in range(1,13):
                history=[(1<<(lap if g<=group else lap-1))-1 for g in range(1,13)]+[final]
                self.assertEqual(verify_itinerary(groups,groups[group][0],history),'lap%d-group%d'%(lap,group))
        for scene,mask in ((62,4),(72,6),(78,7)):
            history=[(1<<mask.bit_count())-1]*12+[mask]
            self.assertEqual(verify_itinerary(groups,scene,history),'lap%d-group13'%mask.bit_count())
        self.assertEqual(verify_itinerary(groups,groups[1][0],[7]*13,True),'pending')

    def test_impossible_fourth_pass_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'third final'):
            verify_itinerary(self.groups(),3,[7]*13)
        with self.assertRaisesRegex(ValueError,'current pass'):
            verify_itinerary(self.groups(),3,[1]+[7]*11+[0])


if __name__=='__main__':unittest.main()
