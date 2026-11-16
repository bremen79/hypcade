#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Optimize attainable input count or score on surviving DAG support.

Nature branches use their best attainable outcome, not their expectation or
worst case. Every branch still needs a surviving continuation. The graph must
describe jointly realizable transition support: merging hidden timing states
can create false possible paths. A ROM graph alone does not discharge that
physical-support obligation.
"""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import rom_proof


def solve(graph, preferred=None, *, objective='highest-score'):
    if objective not in ('shortest','highest-score'):
        raise ValueError('Expected shortest or highest-score objective')
    if preferred is None:
        preferred=[None]*len(graph['states'])
    if len(preferred)!=len(graph['states']):
        raise ValueError('One preferred action index required per state')
    order=rom_proof.decision_dag(graph)['order']
    goals=set(graph['goals'])
    result=[None]*len(graph['states'])
    fields=('best_moves','score_at_best_moves') if objective=='shortest' else ('moves_at_best_score','best_score')
    def key(moves,score):return (moves,-score) if objective=='shortest' else (-score,moves)
    def trajectory(value):return dict(zip(fields,(value[0],-value[1]) if objective=='shortest' else (value[1],-value[0])))
    for u in order:
        award=graph['awards'][u]
        if u in goals:
            result[u]=dict(action=None,label=None,**trajectory(key(0,award)),
                best_targets=[],ranked_actions=[],moves=dict(min=0,max=0),score=dict(min=award,max=award))
            continue
        candidates=[]
        for a,(label,targets) in enumerate(graph['actions'][u]):
            if not targets or any(result[v] is None for v in targets):
                continue
            cost=int(bool(label[0]))
            values=[key(cost+result[v][fields[0]],award+result[v][fields[1]]) for v in targets]
            best=min(values)
            candidates.append((best,repr(label),a,dict(action=a,label=label,
                **trajectory(best),
                best_targets=[v for v,value in zip(targets,values) if value==best],
                moves=dict(min=cost+min(result[v]['moves']['min'] for v in targets),
                           max=cost+max(result[v]['moves']['max'] for v in targets)),
                score=dict(min=award+min(result[v]['score']['min'] for v in targets),
                           max=award+max(result[v]['score']['max'] for v in targets)))))
        if candidates:
            candidates.sort(key=lambda row:(row[0],row[2]!=preferred[u],row[1],row[2]))
            row=candidates[0][3]
            row['ranked_actions']=[dict(action=r[2],**{field:r[3][field] for field in fields},best_targets=r[3]['best_targets'])
                for r in candidates]
            result[u]=row
    return dict(objective='fewest-attainable-inputs' if objective=='shortest' else 'highest-possible-score',states=result,
        tie_break='Highest score along a minimum-input trajectory' if objective=='shortest' else 'Fewest inputs along a trajectory attaining the best possible score',
        scope='Optimal on supplied joint branch support; no probabilities. Physical ROM/timing support must be validated separately. Ranges describe this policy over all supplied branches, not all policies.')
