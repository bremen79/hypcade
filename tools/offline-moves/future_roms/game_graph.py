#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact rational Bellman optimization of a finite acyclic game graph.

Chance outcomes are averaged, never selected by the player. Unknown actions
and incomplete state inventories prevent an optimality certificate.
"""
import argparse
from fractions import Fraction
import json
from pathlib import Path


def solve(graph,objective='highest-score',score_mode='require-fixed'):
    if objective not in ('highest-score','shortest'):raise ValueError('Unknown objective')
    if score_mode not in ('require-fixed','expected'):raise ValueError('Unknown score interpretation')
    states=graph['states'];root=graph['root']
    if root not in states:raise ValueError('Unknown root')
    # Iterative postorder avoids imposing Python's recursion depth on a game.
    color={};order=[];stack=[(root,False)];unresolved=False
    while stack:
        state,finish=stack.pop()
        if finish:
            color[state]=2;order.append(state);continue
        if color.get(state)==2:continue
        if color.get(state)==1:raise ValueError('Cyclic graph: expand it by finite remaining time before solving')
        if state not in states:raise ValueError('Unknown target state: '+state)
        color[state]=1;stack.append((state,True));node=states[state]
        if 'terminal' in node:continue
        if not node.get('expanded',False):unresolved=True
        for action in node.get('actions',[]):
            if not action.get('resolved',False):unresolved=True;continue
            if Fraction(str(action.get('presses',0)))<0:raise ValueError('Negative input cost')
            outcomes=action['outcomes']
            probabilities=[Fraction(str(o['probability'])) for o in outcomes]
            if not probabilities or any(p<=0 for p in probabilities) or sum(probabilities)!=1:
                raise ValueError('Outcome probabilities must be positive and sum exactly to one')
            for outcome in outcomes:
                child=outcome['target']
                if color.get(child)==1:raise ValueError('Cyclic graph: expand it by finite remaining time before solving')
                if color.get(child)!=2:stack.append((child,False))
    values={};policy={};score_bounds={}
    for state in order:
        node=states[state]
        if 'terminal' in node:
            if node['terminal'] not in ('win','loss'):raise ValueError('Unknown terminal type')
            values[state]=None if node['terminal']=='loss' else (Fraction(str(node['score'])),Fraction(0))
            score_bounds[state]=None if values[state] is None else (values[state][0],values[state][0])
            continue
        options=[];bounds=[]
        for action in node.get('actions',[]):
            if not action.get('resolved',False):continue
            if any(values.get(o['target']) is None for o in action['outcomes']):continue
            score=sum(Fraction(str(o['probability']))*values[o['target']][0] for o in action['outcomes'])
            presses=Fraction(str(action.get('presses',0)))+sum(Fraction(str(o['probability']))*values[o['target']][1] for o in action['outcomes'])
            rank=(-score,presses) if objective=='highest-score' else (presses,-score)
            options.append((rank,str(action['id']),(score,presses)))
            bounds.append((min(score_bounds[o['target']][0] for o in action['outcomes']),
                           max(score_bounds[o['target']][1] for o in action['outcomes'])))
        if options:
            _,action,value=min(options);values[state]=value;policy[state]=action
            score_bounds[state]=(max(b[0] for b in bounds),max(b[1] for b in bounds))
        else:values[state]=None;score_bounds[state]=None
    value=values[root]
    bounds=score_bounds[root]
    fixed=bounds is not None and bounds[0]==bounds[1]
    clarification=objective=='highest-score' and score_mode=='require-fixed' and bounds is not None and not fixed
    return dict(objective=objective,winning_policy_found=value is not None,
                expected_final_score=str(value[0]) if value is not None and not clarification else None,
                expected_presses=str(value[1]) if value is not None and not clarification else None,
                fixed_maximum_score=str(bounds[0]) if fixed else None,
                maximum_score_bounds_in_resolved_graph=[str(v) for v in bounds] if bounds else None,
                maximum_score_outcome_independent_in_resolved_graph=fixed,
                score_interpretation_required=clarification,
                policy={} if clarification else policy,reachable_states=len(order),
                model_optimum_proven=bool(graph.get('complete')) and not unresolved and not clarification,
                scope='Exact for the supplied acyclic graph and probabilities; winning actions must avoid every loss outcome. Graph/ROM abstraction completeness requires independent justification.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('graph',type=Path)
    parser.add_argument('--objective',choices=('highest-score','shortest'),default='highest-score')
    parser.add_argument('--score-mode',choices=('require-fixed','expected'),default='require-fixed',
                        help='Default refuses to silently average maxima that depend on chance outcomes')
    args=parser.parse_args();print(json.dumps(solve(json.loads(args.graph.read_text()),args.objective,args.score_mode),indent=2))


if __name__=='__main__':main()
