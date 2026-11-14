#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Move coverage must survive a player's departure from either optimal route."""
import unittest
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from bundle_rom_moves import bundle, ranked_rows, runtime_policy, rule_coverage
from test_rom_export import graph
import export_rom_moves
import rom_tables
import move_arrays


class BranchCoverageTest(unittest.TestCase):
    def test_identical_rom_arrays_share_storage_without_merging_different_policies(self):
        source=('static const uint16_t a[] = {1, 2};\n'
                'static const uint16_t b[] = {1,2};\n'
                'static const uint16_t c[] = {2,1};\n')
        shared,aliases=move_arrays.deduplicate(source)
        self.assertEqual(aliases,{'b':'a'})
        self.assertIn('#define b a',shared)
        self.assertIn('c[] = {2,1}',shared)
        self.assertEqual(move_arrays.deduplicate(shared),(shared,aliases))
    def policy(self, objective, choices):
        return dict(objective=objective, choices=[dict(source=[scene,0],control=control,
                    window=0,outcome=3,rank=0) for scene,control in choices])

    def test_verified_alternate_branch_is_available_to_both_objectives(self):
        # State 2 was reached only by a max-score run, state 3 only by fewest.
        candidates=[((2,100,20,3,8),(10,200)),((3,200,30,3,1),(8,100))]
        for goal in ('shortest','highest-score'):
            rows=ranked_rows(candidates,self.policy(goal,[(2,8),(3,1)]))
            self.assertEqual({r[0] for r in rows},{2,3})

    def test_deliberate_wait_is_preserved_instead_of_copying_other_strategy(self):
        candidates=[((1,100,20,3,16),(15,300)),((2,200,30,3,8),(10,200))]
        shortest=ranked_rows(candidates,self.policy('shortest',[(1,0),(2,8)]))
        maximum=ranked_rows(candidates,self.policy('highest-score',[(1,16),(2,8)]))
        self.assertEqual({r[0] for r in shortest},{2})
        self.assertEqual({r[0] for r in maximum},{1,2})

    def test_missing_timing_calibration_does_not_remove_rom_policy(self):
        self.assertEqual(ranked_rows([((2,100,20,3,8),(10,200))],
                                    self.policy('shortest',[(2,1)])),{})

    def test_outcome_and_live_window_must_match_the_selected_policy(self):
        good=(2,100,20,3,8)
        bad_outcome=(2,100,20,4,8)
        bad_window=(2,100,276,3,8)
        rows=ranked_rows([(r,(10,200)) for r in (good,bad_outcome,bad_window)],
                         self.policy('shortest',[(2,8)]))
        self.assertEqual(set(rows),{good})

    def test_direct_output_merges_both_strategies_and_reuses_route_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory);entries=[]
            for game in ('dle21','ace'):
                rules=output/'rules'/game;rules.mkdir(parents=True)
                (rules/'rules.json').write_text('[]')
                (rules/'inventory.json').write_text(json.dumps(dict(records=[],nodes=[],edges=[])))
                for objective in ('shortest','highest-score'):
                    (rules/(objective+'-policy.json')).write_text(json.dumps(
                        self.policy(objective,[(2,8)])))
                    relative=Path(game)/'ace-d0-00'/objective
                    route=output/relative;route.mkdir(parents=True)
                    move=dict(control=8,frame=100,branch_state=0,timing=20,outcome=3,score_before=0)
                    (route/'route.json').write_text(json.dumps(dict(complete=True,no_life_loss=True,
                        replay=dict(verified=True),configuration=dict(difficulty=0),
                        moves=[move],move_count=1,final_score=100)))
                    (route/'play.jsonl').write_text(json.dumps(dict(type='rom_move',
                        scene=2,step=0,control=8,frame=100))+'\n')
                    (route/'route.trace').write_text('synthetic test trace\n')
                    entries.append(dict(game=game,objective=objective,difficulty=0,
                        directory=str(relative),verified=True,skill='ace',start=0,start_delay=0))
            (output/'report.json').write_text(json.dumps(dict(all_passed=True,
                completed=4,planned=4,failed_runs=0,verified_runs=4,results=entries)))
            with patch('bundle_rom_moves.export_rom_moves.verify'):
                bundle(output,output,output/'arcade_moves.inc')
            for game in ('dle21','ace'):
                data=json.loads((output/(game+'-moves.json')).read_text())
                self.assertEqual(set(data),{'moves','policies','rules','native_rules','rule_policies'})
                self.assertEqual(len(data['moves']),1)
                self.assertEqual(data['policies'],{'shortest':[0],'highest-score':[0]})
            self.assertEqual({p.name for p in output.glob('*.json')},
                {'report.json','generation-verification.json','manifest.json','ace-moves.json','dle21-moves.json','ace-inventory.json','dle21-inventory.json'})
            self.assertEqual((output/'ace/ace-d0-00/shortest/route.trace').read_text(),
                             'synthetic test trace\n')

    def test_unsampled_scenes_and_lower_ranked_actions_are_packaged(self):
        inventory=graph()
        policies={o:rom_tables.policies(inventory,o) for o in export_rom_moves.OBJECTIVES}
        rules=export_rom_moves.compile_rules(inventory,policies)
        native,orders=runtime_policy(rules)
        self.assertIn((27|(10<<7),0,0x81,16),native)
        for order in orders.values():
            rows=[native[i] for i in order]
            self.assertIn((1,0,1,1),rows)
            self.assertIn((1,0,1,8),rows) # Tie is retained, player selects one.
            self.assertNotIn((1,0,2,2),rows) # Death is audited, never suggested.

    def test_removed_rule_or_policy_alternative_fails_coverage(self):
        inventory=graph()
        rules=export_rom_moves.compile_rules(inventory,{o:rom_tables.policies(inventory,o)
                                                       for o in export_rom_moves.OBJECTIVES})
        native,orders=runtime_policy(rules)
        self.assertEqual(rule_coverage(inventory,rules,native,orders)['retained_rules'],len(rules))
        with self.assertRaisesRegex(ValueError,'decoded ROM rule'):
            rule_coverage(inventory,rules[:-1],native,orders)
        incomplete={o:v[:-1] for o,v in orders.items()}
        with self.assertRaisesRegex(ValueError,'ranked ROM alternative'):
            rule_coverage(inventory,rules,native,incomplete)

    def test_incomplete_verification_cannot_publish_merged_moves(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            for game in ('dle21','ace'):
                rules=output/'rules'/game;rules.mkdir(parents=True)
                (rules/'rules.json').write_text('[]')
                (rules/'inventory.json').write_text(json.dumps(dict(records=[],nodes=[],edges=[])))
                for objective in ('shortest','highest-score'):
                    (rules/(objective+'-policy.json')).write_text('{}')
            (output/'report.json').write_text('{"all_passed":false}')
            with patch('bundle_rom_moves.export_rom_moves.verify'):
                with self.assertRaisesRegex(ValueError,'verification is incomplete'):
                    bundle(output,output,output/'arcade_moves.inc')
            self.assertFalse((output/'manifest.json').exists())
            self.assertFalse((output/'arcade_moves.inc').exists())


if __name__=='__main__':unittest.main()
