#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small counterexamples for control reduction and policy comparisons."""
import unittest
import itertools

import rom_proof
import euro_optimality
from rom_controls import simplify_controls, compare_rankings, accepted_regions


class Model:
    def record_for(self, state):
        return dict(trailer=[0, 0, 10, 0], inputs=[dict(rom_control=5, control=1, slot=0,
                    delay_ticks=0, windows=[dict(ticks=2, window=0, outcome=2)])])


def graph(links, awards=None):
    return dict(states=[(0, i) for i in range(3)], awards=awards or [0, 0, 0],
                goals=[2], deaths=[], actions=links)


class StrategyTest(unittest.TestCase):
    def test_italian_pool_bounds_match_independent_full_subset_enumeration(self):
        model=object.__new__(euro_optimality.Model)
        model.data={'roots':[0,1]}
        pools=[dict(entries=[[2,3],[4],[5,6]],initial_count=2),
               dict(entries=[[7],[8,9]],initial_count=1)]
        model.italian_pools=lambda:pools
        graph={'states':list(range(10))}
        values={'fewest':[1,2,1,9,4,3,8,2,7,4],
                'score_at_fewest':[5,6,100,10,80,90,20,70,30,60],
                'fewest_at_score':[1,2,2,9,5,4,8,3,7,5],
                'highest_score':[5,6,101,11,81,91,21,71,31,61]}
        # Enumerate distinct pool positions and each position's paired root.
        choices=[]
        for pool in pools:
            choices.append([roots for entries in itertools.combinations(pool['entries'],pool['initial_count'])
                            for roots in itertools.product(*entries)])
        queues=[sum((list(part) for part in parts),[]) for parts in itertools.product(*choices)]
        result=model.italian_queue_enclosures(graph,values)['objectives']
        for objective,fields in (('shortest',('fewest','score_at_fewest')),
                                 ('highest-score',('fewest_at_score','highest_score'))):
            for metric,field in zip(('moves','score'),fields):
                totals=[sum(values[field][r] for r in [0,1,*q]) for q in queues]
                bounds=result[objective][metric]
                self.assertEqual((bounds['min'],bounds['max']),(min(totals),max(totals)))
                for name in ('min','max'):
                    self.assertIn(bounds[name+'_allocation'],queues)

    def test_diagonal_removed_only_when_values_equal(self):
        g = graph([[((-1, 0, 2), [2]), ((1, 0, 2), [2])], [], []])
        reduced, values, removed = simplify_controls(Model(), g)
        self.assertEqual(len(removed), 1)
        self.assertEqual(reduced['actions'][0], [((1, 0, 2), [2])])
        self.assertEqual(values, rom_proof.solve(g))
        self.assertEqual(len(g['actions'][0]), 2)

    def test_necessary_diagonal_fails_closed(self):
        g = graph([[((-1, 0, 2), [2]), ((1, 0, 2), [1])], [((1, 0, 2), [2])], []])
        with self.assertRaisesRegex(ValueError, 'changes a continuation'):
            simplify_controls(Model(), g)

    def test_empty_window_not_treated_as_executable(self):
        class Empty(Model):
            def record_for(self, state):
                result = super().record_for(state)
                result['inputs'][0]['windows'][0]['ticks'] = 0
                return result
        g = graph([[((1, 0, 2), [2])], [], []])
        with self.assertRaisesRegex(ValueError, 'changes a continuation'):
            simplify_controls(Empty(), g)

    def test_comparison_distinguishes_objectives_and_missing_rows(self):
        g = graph([[((1, 0, 2), [2]), ((2, 0, 1), [1])], [((1, 0, 2), [2])], []], [0, 9, 0])
        local = {o:dict(choices=[dict(source=[0, 0], control=2, window=0, outcome=1, rank=0)])
                 for o in ('shortest', 'highest-score')}
        report, _ = compare_rankings(g, rom_proof.solve(g), local, lambda s:s)
        self.assertEqual(report['shortest']['primary_losses'], 1)
        self.assertEqual(report['highest-score']['primary_losses'], 0)
        self.assertEqual(report['shortest']['missing_local_states'], [1])

    def test_equal_value_tie_is_not_loss(self):
        g = graph([[((1, 0, 2), [2]), ((2, 0, 2), [2])], [], []])
        local = {o:dict(choices=[dict(source=[0, 0], control=2, window=0, outcome=2, rank=0)])
                 for o in ('shortest', 'highest-score')}
        report, _ = compare_rankings(g, rom_proof.solve(g), local, lambda s:s)
        for result in report.values():
            self.assertEqual(result['equal_value_ties'], 1)
            self.assertEqual(result['primary_losses'], 0)

    def test_ignored_descriptor_does_not_shadow_and_timeout_clips(self):
        record = Model().record_for(0)
        entry = record['inputs'][0]
        entry['windows'] = [dict(window=0, outcome=255, ticks=2)]
        later = dict(entry, slot=1, windows=[dict(window=0, outcome=3, ticks=20)])
        record['inputs'].append(later)
        regions = accepted_regions(record)
        self.assertEqual({r['label'] for r in regions}, {(1, 3, 3)})
        self.assertEqual(max(r['end'] for r in regions), 10)


if __name__ == '__main__':
    unittest.main()
