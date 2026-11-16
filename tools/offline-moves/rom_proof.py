#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""ROM decision DAGs and independently checkable Bellman values.

Input actions retain their alternative ROM-selected destinations. Death/recovery
edges affect coverage but are excluded from the surviving-continuation objective.
No CPU snapshots, elapsed-clock graph or probability assumptions are used.
Automatic chains are compressed, not erased: awards and resolved context
changes remain part of the continuation. Full ROM graphs remain auditable.
"""
import collections


def closure(model, seeds, limit=40000):
    states = list(dict.fromkeys(seeds))
    index = {state: i for i, state in enumerate(states)}
    actions, awards, goals, deaths = [], [], [], []
    for state in states:
        if len(states) > limit:
            raise ValueError('Boundary model exceeded its analyzed state budget')
        record = model.record_for(state)
        awards.append(record['award'])
        if model.won(state):
            goals.append(index[state])
        if record['death']:
            deaths.append(index[state])
        choices = []
        for label, destinations in model.actions(state):
            targets = []
            for target in destinations:
                if target not in index:
                    index[target] = len(states)
                    states.append(target)
                targets.append(index[target])
            if targets:
                choices.append((label, sorted(set(targets))))
        actions.append(choices)
    return dict(states=states, actions=actions, awards=awards, goals=goals, deaths=deaths)


def edges(graph):
    return [(u, v, int(bool(label[0]))) for u, choices in enumerate(graph['actions'])
            for label, targets in choices for v in targets]


def decision_dag(graph):
    """Collapse forced chains; classify states without a successful exit as sinks.

    Keep the original graph for ROM audits and expanded per-record policies.
    Compressed edges carry the awards of every skipped record. Automatic
    branches remain explicit, without assigning them a probability law.
    Any cycle that can reach success is an unsupported model, not an edge to
    discard. In particular, a waiting cycle with an available input exit fails.
    """
    count = len(graph['states'])
    goals = set(graph['goals'])
    reverse = [[] for _ in range(count)]
    adjacency = [[] for _ in range(count)]
    for u, choices in enumerate(graph['actions']):
        if u in goals and choices:
            raise ValueError('Successful terminal has outgoing actions')
        for label, targets in choices:
            for v in targets:
                adjacency[u].append(v)
                reverse[v].append(u)
    live = set(goals)
    pending = list(goals)
    for v in pending:
        for u in reverse[v]:
            if u not in live:
                live.add(u)
                pending.append(u)
    # Reverse topological order: destinations before sources. Non-winning
    # automatic loops (and their dead feeders) need no policy or SCC analysis.
    remaining = [sum(v in live for v in targets) for targets in adjacency]
    ready = collections.deque(sorted(u for u in live if not remaining[u]))
    order = []
    while ready:
        v = ready.popleft()
        order.append(v)
        for u in reverse[v]:
            if u in live:
                remaining[u] -= 1
                if not remaining[u]:
                    ready.append(u)
    if len(order) != len(live):
        example = next(u for u in sorted(live) if remaining[u])
        raise ValueError('Cycle can reach a successful end at %r; decision DAG required'
                         % (graph['states'][example],))
    endpoint = [None] * count
    skipped_award = [0] * count
    nodes, actions = [], {}
    for u in order:
        choices = graph['actions'][u]
        forced = (u not in goals and len(choices) == 1 and
                  choices[0][0][0] == 0 and len(choices[0][1]) == 1)
        if forced:
            v = choices[0][1][0]
            endpoint[u] = endpoint[v]
            skipped_award[u] = graph['awards'][u] + skipped_award[v]
        else:
            endpoint[u] = u
            nodes.append(u)
            actions[u] = [(label, [(endpoint[v], skipped_award[v]) for v in targets])
                          for label, targets in choices]
    return dict(nodes=nodes, actions=actions, order=order,
                endpoint=endpoint, skipped_award=skipped_award,
                no_completion=sorted(set(range(count)) - live))


def solve(graph):
    """One backward DAG pass, then expand values to every original ROM record.

    Branch-wise extrema are optimistic bounds, not expectations. `ranked`
    reports unequal branch values; callers must resolve them before claiming
    an executable optimum. Both lexicographic secondary objectives are exact
    for this relaxation.
    """
    dag = decision_dag(graph)
    count = len(graph['states'])
    result = {key: [None] * count for key in
              ('fewest', 'highest_score', 'score_at_fewest', 'fewest_at_score')}
    fewest, score = result['fewest'], result['highest_score']
    short_score, score_short = result['score_at_fewest'], result['fewest_at_score']
    goals = set(graph['goals'])
    for u in dag['nodes']:
        award = graph['awards'][u]
        if u in goals:
            fewest[u] = score_short[u] = 0
            score[u] = short_score[u] = award
            continue
        short_options, score_options = [], []
        for label, targets in dag['actions'][u]:
            cost = int(bool(label[0]))
            for v, skipped in targets:
                if v is None:
                    continue
                short_options.append((cost + fewest[v], -award - skipped - short_score[v]))
                score_options.append((-award - skipped - score[v], cost + score_short[v]))
        fewest[u], negative_score = min(short_options)
        short_score[u] = -negative_score
        negative_score, score_short[u] = min(score_options)
        score[u] = -negative_score
    for u in dag['order']:
        v = dag['endpoint'][u]
        if u != v:
            fewest[u], score_short[u] = fewest[v], score_short[v]
            score[u] = dag['skipped_award'][u] + score[v]
            short_score[u] = dag['skipped_award'][u] + short_score[v]
    verify(graph, result, dag=dag)
    return result


def verify(graph, result, *, dag=None):
    """Check exact Bellman equalities, including ties, on original ROM edges."""
    count = len(graph['states'])
    keys = {'fewest', 'highest_score', 'score_at_fewest', 'fewest_at_score'}
    if set(result) != keys:
        raise ValueError('Invalid potential fields')
    for values in result.values():
        if len(values) != count or any(v is not None and (type(v) is not int or v < 0) for v in values):
            raise ValueError('Invalid potential dimensions/values')
    dag = decision_dag(graph) if dag is None else dag
    live, goals = set(dag['order']), set(graph['goals'])
    for u in range(count):
        actual = (result['fewest'][u], result['score_at_fewest'][u],
                  result['highest_score'][u], result['fewest_at_score'][u])
        if u not in live:
            expected = (None,) * 4
        elif u in goals:
            expected = (0, graph['awards'][u], graph['awards'][u], 0)
        else:
            short_options, score_options = [], []
            for label, targets in graph['actions'][u]:
                cost = int(bool(label[0]))
                for v in targets:
                    if v not in live:
                        continue
                    if any(result[key][v] is None for key in keys):
                        raise ValueError('Missing winning-state potential')
                    short_options.append((cost + result['fewest'][v],
                                          -graph['awards'][u] - result['score_at_fewest'][v]))
                    score_options.append((-graph['awards'][u] - result['highest_score'][v],
                                          cost + result['fewest_at_score'][v]))
            commands, negative_tie_score = min(short_options)
            negative_score, tie_commands = min(score_options)
            expected = commands, -negative_tie_score, -negative_score, tie_commands
        if actual != expected:
            raise ValueError('DAG Bellman equality violated at %r' % (graph['states'][u],))


def ranked(graph, result, objective, supported_only=True):
    """Keep every ranked surviving alternative at every boundary state.

    Return each Nature branch's value explicitly. Disagreement is reported,
    never silently averaged with an invented refresh-register distribution.
    """
    answer, unequal = [], []
    for u, choices in enumerate(graph['actions']):
        rows = []
        for label, targets in choices:
            if supported_only and label[0] == -1:
                continue
            if any(result['fewest'][v] is None for v in targets):
                continue
            cost = int(bool(label[0]))
            if objective == 'shortest':
                values = [(cost + result['fewest'][v], -graph['awards'][u] - result['score_at_fewest'][v]) for v in targets]
            else:
                values = [(-graph['awards'][u] - result['highest_score'][v], cost + result['fewest_at_score'][v]) for v in targets]
            if len(set(values)) > 1:
                unequal.append((u, label, values))
            rows.append((max(values), label, values))
        answer.append(sorted(rows, key=lambda row: (row[0], tuple(-1 if x is None else x for x in row[1]))))
    return answer, unequal
