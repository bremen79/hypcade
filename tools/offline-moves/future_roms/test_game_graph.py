#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact deterministic and stochastic graph optimization, never lucky routing."""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import copy
import unittest
from future_roms.game_graph import solve


def action(name,cost,*targets):
    return dict(id=name,presses=cost,resolved=True,
                outcomes=[dict(target=target,probability=p) for target,p in targets])


class GraphTest(unittest.TestCase):
    def graph(self):
        return dict(root='start',complete=True,states={
            'start':dict(expanded=True,actions=[action('local',1,('scene-b',1)),action('global',2,('scene-c',1))]),
            'scene-b':dict(expanded=True,actions=[action('finish-b',9,('win-b',1))]),
            'scene-c':dict(expanded=True,actions=[action('finish-c',1,('win-c',1))]),
            'win-b':dict(terminal='win',score=10),'win-c':dict(terminal='win',score=105)})

    def test_whole_game_optimum_crosses_scene_boundaries(self):
        for goal in ('highest-score','shortest'):
            result=solve(self.graph(),goal)
            self.assertEqual(result['policy']['start'],'global')
            self.assertEqual(result['expected_final_score'],'105')
            self.assertEqual(result['expected_presses'],'3')
            self.assertTrue(result['model_optimum_proven'])

    def test_random_outcomes_are_averaged_not_chosen(self):
        graph=dict(root='s',complete=True,states={
            's':dict(expanded=True,actions=[action('lottery',1,('big','1/10'),('small','9/10')),
                                           action('certain',2,('mid',1))]),
            'big':dict(terminal='win',score=100),'small':dict(terminal='win',score=0),
            'mid':dict(terminal='win',score=20)})
        result=solve(graph,score_mode='expected')
        self.assertEqual(result['policy']['s'],'certain')
        result=solve(graph,'shortest')
        self.assertEqual(result['policy']['s'],'lottery')
        self.assertEqual(result['expected_final_score'],'10')

    def test_exact_fractions_and_shared_targets(self):
        graph=self.graph()
        graph['states']['start']['actions']=[action('mix',1,('win-b','1/3'),('win-c','2/3'))]
        self.assertEqual(solve(graph,score_mode='expected')['expected_final_score'],'220/3')

    def test_score_invariance_is_checked_instead_of_assumed(self):
        graph=dict(root='s',complete=True,states={
            's':dict(expanded=True,actions=[action('random',1,('a','1/2'),('b','1/2'))]),
            'a':dict(terminal='win',score=10),'b':dict(terminal='win',score=20)})
        result=solve(graph)
        self.assertTrue(result['score_interpretation_required'])
        self.assertEqual(result['maximum_score_bounds_in_resolved_graph'],['10','20'])
        self.assertIsNone(result['expected_final_score'])
        self.assertFalse(result['model_optimum_proven'])
        graph['states']['a']['score']=20
        result=solve(graph)
        self.assertEqual(result['fixed_maximum_score'],'20')
        self.assertTrue(result['model_optimum_proven'])

    def test_unknown_actions_prevent_a_certificate(self):
        graph=self.graph();graph['states']['start']['actions'].append(dict(id='unknown',resolved=False))
        result=solve(graph)
        self.assertTrue(result['winning_policy_found'])
        self.assertFalse(result['model_optimum_proven'])

    def test_incomplete_inventory_prevents_a_certificate(self):
        graph=self.graph();graph['complete']=False
        self.assertFalse(solve(graph)['model_optimum_proven'])

    def test_cycles_require_finite_horizon_expansion(self):
        graph=self.graph();graph['states']['scene-b']['actions']=[action('loop',0,('start',1))]
        with self.assertRaisesRegex(ValueError,'Cyclic graph'):solve(graph)

    def test_invalid_probabilities_and_missing_targets_fail(self):
        for outcomes in [[('win-b','1/3')],[('win-b',0),('win-c',1)],[('unknown',1)]]:
            graph=self.graph();graph['states']['start']['actions']=[action('bad',1,*outcomes)]
            with self.assertRaises(ValueError):solve(graph)

    def test_loss_is_not_a_valid_death_free_continuation(self):
        graph=self.graph();graph['states']['loss']=dict(terminal='loss')
        graph['states']['start']['actions'].insert(0,action('risky',0,('win-c','9/10'),('loss','1/10')))
        self.assertEqual(solve(graph)['policy']['start'],'global')


if __name__=='__main__':unittest.main()
