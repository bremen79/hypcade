#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare the two-stream reduction with chronological exhaustive DAG solving."""
from functools import lru_cache
import unittest

from dl1_allocation import allocate, allocate_three, verify_witness, verify_three, add


def transitions():
    # Only one optional room. Its resource is shared between both rounds.
    result={}
    for used in range(32):
        for mask in range(7):
            rows=[((i,mask|(1<<i),used),i) for i in range(3) if not mask&(1<<i)]
            if mask and not used&1:rows.append(((3,mask,used|1),3))
            result[used,mask]=rows
    return result


def exhaustive(groups, table, costs, normal, first_choice=None):
    @lru_cache(None)
    def solve(visit, group, masks, used):
        if visit==3:return (0,0)
        choices=table[used,masks[group]]
        if visit==0:
            choices=[((i,1<<i,used),i) for i in range(3)
                     if group or first_choice is None or i==first_choice]
        options=[]
        for (choice,mask,next_used),_ in choices:
            root=groups[group][choice]+(0 if visit==0 and group<normal else 40) if choice<3 else 80+choice-3
            following=list(masks);following[group]=mask
            next_group=(group+1)%len(groups)
            options.append(add(costs[root],solve(visit+int(not next_group),next_group,tuple(following),next_used)))
        return min(options)
    return solve(0,0,(0,)*len(groups),0)


class AllocationTest(unittest.TestCase):
    def setUp(self):
        self.groups=[[1,2,3],[4,5,6]]
        self.table=transitions()
        self.costs={r:((r*7)%11, -(r*17)%29) for r in range(85)}

    def test_both_rounds_match_chronological_graph(self):
        for normal in (0,1,2):
            for sign in (1,-1):
                costs={r:(sign*a,sign*b) for r,(a,b) in self.costs.items()}
                result=allocate(self.groups,self.table,costs,normal)
                self.assertEqual(result['value'],exhaustive(self.groups,self.table,costs,normal))
                verify_witness(result,self.groups,self.table,costs,normal)

    def test_fixed_first_scene_is_retained(self):
        for first in range(3):
            result=allocate(self.groups,self.table,self.costs,1,first_choice=first)
            self.assertEqual(result['groups'][0]['first'],first)
            self.assertEqual(result['value'],exhaustive(self.groups,self.table,self.costs,1,first))

    def test_unused_boundary_bits_cannot_give_free_optional_rooms(self):
        result=allocate(self.groups,self.table,{r:(1,0) for r in range(85)},0)
        self.assertEqual(result['value'],(6,0))
        self.assertIn(result['boundary'],(0,1))
        self.assertIn(result['final_used'],(0,1))

    def test_invalid_witness_rejected(self):
        result=allocate(self.groups,self.table,self.costs,0)
        result['value']=(999,999)
        with self.assertRaisesRegex(ValueError,'reward mismatch'):
            verify_witness(result,self.groups,self.table,self.costs,0)

    def test_three_streams_allow_first_visit_optional_rooms(self):
        table={key:list(rows) for key,rows in self.table.items()}
        for used in range(32):
            if not used&1:table[used,0].append(((3,0,used|1),3))
        # Independent chronological graph, with first visits now using the
        # same actual selector instead of assuming they are always regular.
        @lru_cache(None)
        def solve(visit,group,masks,used):
            if visit==3:return (0,0)
            options=[]
            for (choice,mask,next_used),_ in table[used,masks[group]]:
                root=80+choice-3 if choice>=3 else self.groups[group][choice]+40
                following=list(masks);following[group]=mask
                nxt=(group+1)%len(self.groups)
                options.append(add(self.costs[root],solve(visit+int(not nxt),nxt,tuple(following),next_used)))
            return min(options)
        result=allocate_three(self.groups,[table]*2,table,self.costs,0)
        self.assertEqual(result['value'],solve(0,0,(0,0),0))
        verify_three(result,[table]*2,table,self.costs,self.groups,0)

    def test_three_streams_reduce_to_two_when_first_visit_is_regular(self):
        for normal in (0,1,2):
            result=allocate_three(self.groups,[self.table]*2,self.table,self.costs,normal)
            self.assertEqual(result['value'],exhaustive(self.groups,self.table,self.costs,normal))
            verify_three(result,[self.table]*2,self.table,self.costs,self.groups,normal)

    def test_observed_three_pass_prefixes_against_chronological_enumeration(self):
        table={key:list(rows) for key,rows in self.table.items()}
        for used in range(32):
            if not used&1:table[used,0].append(((3,0,used|1),3))
        for normal in (0,1):
            cases=[{}, {(0,0):dict(scene=80,mask=0,used=1)},
                {(1,1):dict(scene=45,mask=3,used=0)},
                {(2,0):dict(scene=80,mask=3,used=1)},
                {(0,0):dict(scene=41 if not normal else 1,mask=2,used=0)},
                {(0,0):dict(scene=80,mask=0,used=1),(2,0):dict(scene=80,mask=3,used=1)}]
            for known in cases:
                @lru_cache(None)
                def chronological(lap,g,masks,used):
                    if lap==3:return (0,0)
                    options=[]
                    for (choice,mask,nxt_used),_ in table[used,masks[g]]:
                        root=80+choice-3 if choice>=3 else self.groups[g][choice]+(0 if lap==0 and g<normal else 40)
                        observed=known.get((lap,g))
                        if observed and (root,mask,nxt_used)!=(observed['scene'],observed['mask'],observed['used']):
                            continue
                        following=list(masks);following[g]=mask
                        nxt=(g+1)%len(self.groups)
                        tail=chronological(lap+int(not nxt),nxt,tuple(following),nxt_used)
                        if tail is not None:options.append(add(self.costs[root],tail))
                    return min(options) if options else None
                expected=chronological(0,0,(0,0),0)
                if expected is None:
                    with self.assertRaises(ValueError):
                        allocate_three(self.groups,[table]*2,table,self.costs,normal,known=known)
                else:
                    result=allocate_three(self.groups,[table]*2,table,self.costs,normal,known=known)
                    self.assertEqual(result['value'],expected)
                    verify_three(result,[table]*2,table,self.costs,self.groups,normal)


if __name__=='__main__':unittest.main()
