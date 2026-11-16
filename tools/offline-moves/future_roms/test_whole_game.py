#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Whole-game rewards, context preservation, budgets and independent replay."""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from future_roms import whole_game as w


def graph():
    records=[]
    for address,award in enumerate((0,10,5)):
        records.append(dict(address=address,award=award,death=False,system=False,
                            scene_exit=address!=0,inputs=[]))
    records[0]['inputs']=[dict(control=1,windows=[dict(window=0,ticks=10,outcome=1)]),
                          dict(control=8,windows=[dict(window=0,ticks=10,outcome=130)])]
    return dict(records=records,nodes=[dict(scene=1,step=0,address=0),dict(scene=1,step=1,address=1),
                                      dict(scene=2,step=0,address=2)],
                edges=[dict(source=[1,0],target=[1,1],control=1,window=0,outcome=1),
                       dict(source=[1,0],target=[2,0],control=8,window=0,outcome=130)])


class WholeGameTest(unittest.TestCase):
    def test_terminal_objectives_and_ties(self):
        self.assertLess(w.objective_key(105,9,'highest-score'),w.objective_key(10,1,'highest-score'))
        self.assertLess(w.objective_key(10,1,'shortest'),w.objective_key(105,9,'shortest'))
        self.assertLess(w.objective_key(20,2,'shortest'),w.objective_key(10,2,'shortest'))

    def test_unranked_death_edges_are_not_pruned_by_local_policy(self):
        data=graph();data['records'][2]['death']=True
        self.assertIn((8,0,130),w.alternatives(data)[(1,0)])
        self.assertIn((0,0,0),w.alternatives(data)[(1,0)])

    def test_shared_player_instrumentation_fails_closed_when_source_changes(self):
        source=(w.ROOT/'rom_routes.c').read_text()
        instrumented=w.player_source(source)
        self.assertIn('whole_branch(&m,g,checkpoint,checkpoint_cycle,best)',instrumented)
        self.assertIn('if(forcing)forced_active=false;',instrumented)
        self.assertIn('(!forcing && !rom_effective',instrumented)
        self.assertIn('origin.checkpoint_cycle',instrumented)
        with self.assertRaisesRegex(ValueError,'Shared ROM player changed'):
            w.player_source(source.replace('bool committed=false;','bool committed = false;'))

    def run_search(self,objective,replay_fails=False):
        instances=[]
        class Worker:
            def __init__(self,command,log):
                instances.append(self);self.trace=Path(command[-2]);self.run=-1;self.closed=False
            def send(self,command):
                if command in ('KEEP','SKIP'):
                    self.events=([dict(type='checkpoint',offset=self.run*128)] if command=='KEEP' else [])+[self.result]
                    return
                self.run+=1
                alt=command.startswith('RUN ') and command.split()[2]=='8'
                self.result=dict(type='result',run=self.run,complete=True,trace_limit=False,
                                 score=105 if alt else 10,moves=(2 if alt else 4))
                self.trace.write_text('synthetic independently replayed route\n')
                # Same scene/step, distinct full-machine context: neither may
                # disappear through a scene-only merge.
                self.events=[dict(type='node',scene=1,step=0,moves=self.run,bytes=128,
                                  score=0,cycles=self.run+1,preferred=[1,0,1],key='01' if self.run==0 else '02')]
            def read(self):return self.events.pop(0)
            def close(self):self.closed=True
        def replay(*args):
            if replay_fails:raise ValueError('Independent replay failed')
            r=instances[-1].result
            return dict(verified=True,score=r['score'],move_count=r['moves'])
        with tempfile.TemporaryDirectory() as folder:
            args=SimpleNamespace(output=Path(folder),rom=Path('fixture.zip'),game='ace',skill='ace',difficulty=0,
                start_delay=0,max_seconds=3600,trial_timeout=10,max_nodes=20,max_store_mib=1,max_rollouts=2,wall_seconds=0)
            with patch.object(w,'Worker',Worker),patch.object(w,'replay',side_effect=replay) as checked:
                if replay_fails:
                    with self.assertRaisesRegex(ValueError,'Independent replay failed'):
                        w.search(args,objective,Path('worker'),Path('verifier'),graph())
                    self.assertTrue(instances[0].closed);return
                result=w.search(args,objective,Path('worker'),Path('verifier'),graph())
                self.assertEqual(checked.call_count,2)
                self.assertTrue(instances[0].closed)
                self.assertEqual(result['nodes'],2)
                self.assertFalse(result['global_optimum_proven'])
                self.assertFalse(result['model_optimum_proven'])
                self.assertIn('rollout-budget',result['limits_reached'])
                self.assertEqual(json.loads((Path(folder)/objective/'report.json').read_text())['whole_game']['score'],105)
                return result

    def test_lower_local_award_can_produce_higher_whole_game_score(self):
        result=self.run_search('highest-score')
        self.assertEqual((result['local']['score'],result['whole_game']['score']),(10,105))

    def test_more_attractive_local_route_can_require_more_total_presses(self):
        result=self.run_search('shortest')
        self.assertEqual(result['presses_saved'],2)

    def test_winning_candidate_cannot_bypass_independent_replay(self):
        self.run_search('highest-score',replay_fails=True)


if __name__=='__main__':unittest.main()
