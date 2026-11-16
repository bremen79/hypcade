#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Separate distribution-independent control certificates from evaluation.

Sufficient, deliberately conservative test: a fixed policy's worst supported
lexicographic outcome must beat every competing action's optimistic ROM bound.
Distributions may depend on the selected action and on earlier history. Failed
tests are inconclusive, never evidence that probabilities change the policy.
"""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import rom_proof


def audit_fewest_tolerance(graph, policy, tolerance=1):
    """One total remaining-game allowance, never an allowance per decision.

    For any action/history-dependent Nature law, optimal expectation is at
    least the relaxed best-branch cost. The fixed policy's expectation is at
    most its worst supported total. Their difference bounds its regret.
    No probability model or successor optimality assumption is required.
    """
    if type(tolerance) is not int or tolerance<0:
        raise ValueError('Expected a nonnegative integer input tolerance')
    if len(policy)!=len(graph['states']):raise ValueError('One action index per state required')
    relaxed=rom_proof.solve(graph);order=rom_proof.decision_dag(graph)['order']
    goals=set(graph['goals']);results=[None]*len(policy)
    for u in order:
        award=graph['awards'][u]
        if u in goals:
            moves=dict(min=0,max=0);score=dict(min=award,max=award)
        else:
            selected=policy[u]
            if selected is None:continue
            choices=graph['actions'][u]
            if type(selected) is not int or not 0<=selected<len(choices):
                raise ValueError('Invalid selected action')
            label,targets=choices[selected];children=[results[v] for v in targets]
            if not children or any(c is None for c in children):continue
            moves={k:int(bool(label[0]))+f(c['moves'][k] for c in children)
                   for k,f in (('min',min),('max',max))}
            score={k:award+f(c['score'][k] for c in children)
                   for k,f in (('min',min),('max',max))}
        lower=relaxed['fewest'][u]
        regret=moves['max']-lower
        results[u]=dict(lower_optimal_expected_inputs=lower,moves=moves,score=score,
            expected_regret_upper_bound=regret,certified=regret<=tolerance,tolerance=tolerance)
    return results


def audit(graph, policy, objective='shortest'):
    if objective not in ('shortest', 'highest-score'):
        raise ValueError('Unknown objective')
    if len(policy) != len(graph['states']):
        raise ValueError('One policy action index required per state')
    relaxed = rom_proof.solve(graph)
    order = rom_proof.decision_dag(graph)['order']
    goals = set(graph['goals'])
    results = [None] * len(policy)

    def pair(moves, score):
        return (moves, -score) if objective == 'shortest' else (-score, moves)

    def optimistic(v):
        if objective == 'shortest':
            return pair(relaxed['fewest'][v], relaxed['score_at_fewest'][v])
        return pair(relaxed['fewest_at_score'][v], relaxed['highest_score'][v])

    for u in order:
        award = graph['awards'][u]
        if u in goals:
            value = pair(0, award)
            results[u] = dict(low=value, high=value, local=True, certified=True, blockers=[],
                             moves=dict(min=0, max=0), score=dict(min=award, max=award))
            continue
        selected = policy[u]
        if selected is None:
            continue
        choices = graph['actions'][u]
        if not 0 <= selected < len(choices):
            raise ValueError('Invalid policy action')
        label, targets = choices[selected]
        children = [results[v] for v in targets]
        if not children or any(c is None for c in children):
            continue
        delta = pair(int(bool(label[0])), award)
        def add(value):
            return tuple(a+b for a, b in zip(delta, value))
        low = add(min(c['low'] for c in children))
        high = add(max(c['high'] for c in children))
        blockers = []
        for a, (lab, ts) in enumerate(choices):
            if a == selected or any(relaxed['fewest'][v] is None for v in ts):
                continue
            # No cancellation merely because two actions reach the same
            # semantic successor: hidden timing can change its future law.
            d = pair(int(bool(lab[0])), award)
            bound = tuple(a+b for a, b in zip(d, min(optimistic(v) for v in ts)))
            if high > bound:
                blockers.append(dict(action=a, optimistic=bound))
        results[u] = dict(low=low, high=high, local=not blockers,
                          certified=not blockers and all(c['certified'] for c in children),
                          blockers=blockers,
                          moves=dict(min=int(bool(label[0]))+min(c['moves']['min'] for c in children),
                                     max=int(bool(label[0]))+max(c['moves']['max'] for c in children)),
                          score=dict(min=award+min(c['score']['min'] for c in children),
                                     max=award+max(c['score']['max'] for c in children)))
    return results
