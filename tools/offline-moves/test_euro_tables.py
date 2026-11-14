#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
import euro_tables as e


class EuroTablesTest(unittest.TestCase):
    def test_fixed_records_preserve_immediate_target_and_zero_flag_input(self):
        rom=bytearray(b'\xff'*32768)
        rom[0x2000:0x2002]=(36).to_bytes(2,'little')
        for i in range(39):rom[0x2002+2*i:0x2004+2*i]=(6).to_bytes(2,'little')
        at=e.BASE+5*32
        rom[at:at+6]=bytes([100,0,0,12,0x50,0x03])
        rom[at+30:at+32]=b'\0\0'
        rom[at+6+2*5:at+8+2*5]=(0x8006).to_bytes(2,'little')
        rec=e.inventory(rom)['records'][0]
        self.assertEqual(rec['inputs'],[dict(slot=5,control=4,target=0x8006)])
        self.assertEqual(rec['award'],350)
        rom[at+6:at+8]=b'\0\0'
        with self.assertRaisesRegex(ValueError,'Unmapped'):e.inventory(rom)

    def test_bcd_validation(self):
        self.assertEqual(e.bcd(0x3550),3550)
        with self.assertRaises(ValueError):e.bcd(0xabcd)

    def test_rankings_keep_all_safe_alternatives_and_required_zero_score(self):
        def rec(i,award=0,default=0,inputs=(),death=False):
            return dict(id=i,award=award,default=default,inputs=list(inputs),death=death,victory=False)
        data=dict(game='lair_ita',roots=[6],records=[
            rec(6,default=9,inputs=[dict(control=1,target=7),dict(control=2,target=8),dict(control=4,target=9)]),
            rec(7,award=100),rec(8,award=500,default=9,inputs=[dict(control=16,target=7)]),rec(9,death=True)])
        short=e.policies(data,'shortest');high=e.policies(data,'highest-score')
        self.assertEqual(short['choices'][0]['control'],1)
        self.assertEqual(high['choices'][0]['control'],2)
        self.assertEqual({c['control'] for c in high['choices'] if c['id']==6},{1,2})
        self.assertTrue(any(c['id']==8 and c['control']==16 for c in short['choices']))
        table=e.compact(data,{'shortest':short,'highest-score':high})
        self.assertEqual(len(table['rules']),len(set(tuple(r) for r in table['rules'])))
        self.assertEqual(set(table['policies']['shortest']),set(table['policies']['highest-score']))

    def test_unknown_cycles_are_rejected_instead_of_silently_dropping_moves(self):
        data=dict(roots=[6],records=[dict(id=6,award=0,default=6,inputs=[],death=False,victory=False)])
        with self.assertRaisesRegex(ValueError,'cycle'):e.policies(data,'shortest')


if __name__=='__main__':unittest.main()
