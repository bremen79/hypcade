#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic ROM records: decode bounds, alternate controls and route objectives."""
import unittest
import rom_tables as r

class RomTablesTest(unittest.TestCase):
    def test_record_windows_and_score(self):
        rom=bytearray(0x3000);rom[0x2304:0x2306]=(684).to_bytes(2,'little')
        # UP: two outcomes; two timing windows choose outcomes 1 then 0.
        payload=bytes([0xa1,0x06,3,4,5,10,20,1,7,50,0,0,0,0])
        rom[0x2500:0x2500+len(payload)]=payload
        d=r.decode_record(rom,0x2500,'dle21')
        self.assertEqual(d['award'],684)
        self.assertEqual(d['inputs'][0]['delay_ticks'],5)
        self.assertEqual(d['inputs'][0]['windows'],[dict(window=0,ticks=10,outcome=4),dict(window=1,ticks=20,outcome=3)])
        self.assertEqual(d['end'],0x2500+len(payload))

    def graph(self):
        nodes=[dict(scene=1,step=i,address=i) for i in range(5)]
        records=[dict(address=i,award=(100 if i==3 else 10 if i==1 else 0),death=i==4,system=False,scene_exit=i in (1,3,4)) for i in range(5)]
        edges=[dict(source=[1,a],target=[1,b],control=c,window=0,outcome=b) for a,b,c in [(0,1,1),(0,2,8),(0,2,16),(2,3,4),(0,4,2)]]
        return dict(nodes=nodes,records=records,edges=edges)

    def test_objectives_keep_alternatives_and_exclude_deaths(self):
        d=self.graph();short=r.policies(d,'shortest');high=r.policies(d,'highest-score')
        a=[x for x in short['choices'] if x['source']==[1,0]]
        b=[x for x in high['choices'] if x['source']==[1,0]]
        self.assertEqual(a[0]['control'],1);self.assertEqual(b[0]['control'],8)
        self.assertEqual({x['control'] for x in a},{1,8,16})
        self.assertEqual({x['control'] for x in b},{1,8,16})

    def test_required_zero_score_action_is_preserved(self):
        d=self.graph();d['records'][1]['award']=0;d['edges']=d['edges'][:1]
        p=r.policies(d,'shortest')
        self.assertEqual(p['choices'][0]['control'],1)
        self.assertEqual(p['choices'][0]['remaining_score'],0)

    def test_same_scene_restart_is_dispatch_boundary(self):
        d=self.graph();d['edges']=[dict(source=[1,2],target=[1,0],control=0,window=0,outcome=0x81)]
        p=r.policies(d,'shortest');self.assertEqual(len(p['choices']),1)
        self.assertEqual(p['choices'][0]['control'],0)

    def test_invalid_selector_rejected(self):
        rom=bytearray(0x3000);rom[0x2500:0x2505]=bytes([0x81,0x0d,0,0,1])
        with self.assertRaisesRegex(ValueError,'selector'):r.decode_record(rom,0x2500,'dle21')

if __name__=='__main__':unittest.main()
