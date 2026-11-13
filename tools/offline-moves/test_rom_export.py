#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Export completeness, unsupported timing, ties and reproducible packages."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import export_rom_moves as exporter
import rom_tables


def graph():
    def entry(slot, control, ticks, outcome, extra=None):
        return dict(slot=slot, control=control, rom_control=control,
                    header=0x81 if extra is None else 0x91, extra=extra,
                    selector=1, delay_ticks=5,
                    windows=[dict(window=0,ticks=ticks,outcome=outcome)])
    records = [dict(address=i, inputs=[], trailer=[0,255,0,0,0,0,0],
                    award=0, death=False, scene_exit=False, system=False) for i in range(4)]
    # Equal, zero-score winning alternatives; a death and an empty window.
    records[0]['inputs']=[entry(0,1,10,1), entry(1,8,10,1,0x40),
                          entry(2,2,5,2), entry(3,4,0,1)]
    records[1]['scene_exit']=True
    records[2]['death']=True
    # A separate scene which no successful sample need ever visit.
    records[3]['inputs']=[entry(0,16,20,0x81)]
    nodes=[dict(scene=1,step=i,address=i) for i in range(3)]+[dict(scene=27,step=10,address=3)]
    edges=[dict(source=[1,0],target=[1,target],control=control,window=slot*3,outcome=target)
           for slot,control,target in [(0,1,1),(1,8,1),(2,2,2)]]
    edges.append(dict(source=[27,10],target=[1,0],control=16,window=0,outcome=0x81))
    return dict(game='ace', groups=[dict(scene=1),dict(scene=27)],
                records=records,nodes=nodes,edges=edges,unresolved_targets=[])


class ExportTest(unittest.TestCase):
    def rules(self):
        data=graph()
        return exporter.compile_rules(data,{goal:rom_tables.policies(data,goal) for goal in exporter.OBJECTIVES})

    def test_unvisited_scene_and_equal_zero_score_alternatives_survive(self):
        rules=self.rules()
        self.assertTrue(any(r['source']==[27,10] and r['control']==16 for r in rules))
        winning=[r for r in rules if r['source']==[1,0] and r['classification']=='candidate']
        self.assertEqual({r['control'] for r in winning},{1,8})
        for rule in winning:
            self.assertEqual(set(rule['objectives']),set(exporter.OBJECTIVES))
            self.assertEqual(rule['target_award'],0)
            self.assertFalse(rule['causal_score_gain_proven'])

    def test_condition_is_not_replaced_by_observed_branch_or_frame(self):
        rule=next(r for r in self.rules() if r['id']=='1:0:1:0')
        self.assertEqual(rule['loader']['extra'],0x40)
        self.assertEqual(rule['rom_slot'],1)
        self.assertIsNone(rule['timing']['accepted_frame'])
        self.assertNotIn('branch_state',rule)
        self.assertEqual(rule['timing']['basis'],'rom-before-runtime-adjustment')

    def test_death_and_empty_windows_remain_visible_but_unranked(self):
        rules={r['id']:r for r in self.rules()}
        self.assertEqual(rules['1:0:2:0']['classification'],'death')
        self.assertEqual(rules['1:0:3:0']['classification'],'empty-window')
        self.assertEqual(rules['1:0:2:0']['objectives'],{})
        self.assertEqual(rules['1:0:3:0']['objectives'],{})

    def test_all_windows_and_default_records_are_accounted_for(self):
        rules=self.rules()
        self.assertEqual(len(rules),4+5)
        self.assertEqual(len({r['id'] for r in rules}),len(rules))

    def test_dispatch_record_does_not_invent_a_timeout_edge(self):
        data=graph();data['records'][1]['trailer'][1]=0x81
        rules=exporter.compile_rules(data,{goal:rom_tables.policies(data,goal) for goal in exporter.OBJECTIVES})
        rule=next(r for r in rules if r['id']=='1:1:wait')
        self.assertEqual(rule['classification'],'source-dispatch')
        self.assertIsNone(rule['target'])
        self.assertFalse(rule['dispatch'])

    def package(self,folder):
        with patch.object(exporter.move_tools,'identity',return_value=[dict(name='synthetic')]), \
             patch.object(rom_tables,'load',return_value=b''), \
             patch.object(rom_tables,'inventory',return_value=graph()):
            return exporter.export(Path('not-a-real-rom.zip'),'ace',folder)

    def test_reproducible_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            a,b=Path(temp)/'a',Path(temp)/'b'
            self.package(a);self.package(b)
            self.assertEqual({p.name:p.read_bytes() for p in a.iterdir()},
                             {p.name:p.read_bytes() for p in b.iterdir()})
            exporter.verify(a)
            with self.assertRaisesRegex(ValueError,'already exists'):self.package(a)

    def test_rehashed_omission_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'export';self.package(folder)
            rules=json.loads((folder/'rules.json').read_text());rules.pop()
            (folder/'rules.json').write_text(json.dumps(rules))
            manifest=json.loads((folder/'manifest.json').read_text())
            manifest['files']['rules.json']=hashlib.sha256((folder/'rules.json').read_bytes()).hexdigest()
            (folder/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'cover the decoded graph'):exporter.verify(folder)

    def test_unresolved_graph_not_published(self):
        data=copy.deepcopy(graph());data['unresolved_targets']=[dict(source=[1,0],target=[99,0])]
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(exporter.move_tools,'identity',return_value=[]), \
             patch.object(rom_tables,'load',return_value=b''), \
             patch.object(rom_tables,'inventory',return_value=data):
            folder=Path(temp)/'export'
            with self.assertRaisesRegex(ValueError,'Unresolved'):exporter.export(Path('x'),'ace',folder)
            self.assertFalse(folder.exists())


if __name__=='__main__':unittest.main()
