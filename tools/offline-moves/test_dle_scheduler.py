#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Counterexamples for the scheduler's pointwise, probability-free checker."""
import copy
import unittest

from dle_scheduler_graph import verify


def certificate():
    value=dict(fewest=2,score_at_fewest=30,highest_score=50,fewest_at_score=3)
    return dict(states=['root'],potential={k:[v] for k,v in value.items()},initial=value,
                initial_bridge={k:0 for k in value},
                branches=[[dict(room=1,exits=[dict(effect=['win'],target=None,room_values=value)])]])


class SchedulerTest(unittest.TestCase):
    def test_identical_nature_branches_need_no_probability_law(self):
        data=certificate();data['branches'][0].append(copy.deepcopy(data['branches'][0][0]));verify(data)

    def test_one_unequal_nature_alternative_is_rejected(self):
        data=certificate();other=copy.deepcopy(data['branches'][0][0])
        other['exits'][0]['room_values']['fewest']=3
        data['branches'][0].append(other)
        with self.assertRaisesRegex(ValueError,'Nature alternative'):verify(data)

    def test_damaged_secondary_value_is_rejected(self):
        data=certificate();data['potential']['score_at_fewest'][0]=31
        with self.assertRaisesRegex(ValueError,'Bellman'):verify(data)

    def test_zero_cost_self_cycle_cannot_certify_a_game(self):
        data=certificate();edge=data['branches'][0][0]['exits'][0]
        edge['target']=0;edge['room_values']={k:0 for k in data['potential']}
        with self.assertRaisesRegex(ValueError,'Cyclic'):verify(data)

    def test_initial_prefix_must_be_counted(self):
        data=certificate();data['initial_bridge']['fewest']=1
        with self.assertRaisesRegex(ValueError,'bridge'):verify(data)


if __name__=='__main__':unittest.main()
