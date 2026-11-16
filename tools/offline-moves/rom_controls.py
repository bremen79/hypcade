#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""ROM input regions, safe control reduction and policy-value comparisons."""
import copy
import rom_proof

OBJECTIVES = ('shortest', 'highest-score')


def accepted_regions(record):
    """Nominal ROM ticks with first-descriptor priority, no timing shifts.

    FF outcomes do not consume an input and cannot shadow later descriptors.
    Harder-mode loader transformations remain a separate native audit.
    """
    duration = record['trailer'][2] | record['trailer'][3] << 8
    intervals = []
    for entry in record['inputs']:
        start = entry['delay_ticks']
        for window in entry['windows']:
            end = start + window['ticks']
            label = entry['control'], entry['slot'] * 3 + window['window'], window['outcome']
            intervals.append((label, start, end))
            start = end
    cuts = sorted({0, duration, *(t for _, a, b in intervals for t in (a, b) if 0 <= t <= duration)})
    result = []
    for a, b in zip(cuts, cuts[1:]):
        used = set()
        for label, start, end in intervals:
            control, _, outcome = label
            if control is not None and outcome != 255 and start <= a < end and control not in used:
                used.add(control)
                result.append(dict(label=label, start=a, end=b))
    return result


def simplify_controls(model, graph):
    """Remove diagonals/empty windows only if every Bellman value is preserved.

    The complete decoded inventory remains separate. This proves a control
    restriction preserves the boundary optimum; it does not prove delivery at
    every physical CPU phase, nor equivalence of post-death score gates.
    """
    reduced = copy.deepcopy(graph)
    removed = []
    for u, actions in enumerate(graph['actions']):
        kept = []
        record = model.record_for(graph['states'][u])
        regions = ({tuple(r['label']) for r in accepted_regions(record)}
                   if record.get('inputs') else set())
        for label, targets in actions:
            if label[0] == 0:
                kept.append((label, targets))
                continue
            slot, window = divmod(label[1], 3)
            entry = record['inputs'][slot]
            if label[0] == -1 and entry['rom_control'] not in (5, 6, 9, 10):
                raise ValueError('Unknown control cannot be discarded as a diagonal')
            if label[0] == -1 or label not in regions:
                removed.append(dict(state=u, label=label, reason='diagonal' if label[0] == -1 else 'no-nominal-acceptance-region'))
            else:
                kept.append((label, targets))
        reduced['actions'][u] = kept
    original_values = rom_proof.solve(graph)
    values = rom_proof.solve(reduced)
    if values != original_values:
        raise ValueError('Control restriction changes a continuation value; retain its inputs')
    return reduced, values, removed


def compare_rankings(graph, values, local, source_key, *, euro=False):
    """Measure local first actions using complete continuation action values.

    Distinguish equal-value tie changes from primary and secondary losses.
    The comparison is against freshly reconstructed local search, not APK bytes.
    """
    reports, policies = {}, {}
    for objective in OBJECTIVES:
        local_rows = {}
        for row in local[objective]['choices']:
            key = row['id'] if euro else tuple(row['source'])
            label = (row['control'], 0, row['target']) if euro else (row['control'], row['window'], row['outcome'])
            local_rows.setdefault(key, []).append((row['rank'], label))
        rankings, unequal = rom_proof.ranked(graph, values, objective)
        differences, missing, counts = [], [], dict(compared_states=0, primary_losses=0, secondary_losses=0, equal_value_ties=0)
        policy = []
        for u, rows in enumerate(rankings):
            policy.append(dict(state=u, ranked=[dict(label=label, lexicographic_value=value,
                branch_values=branches) for value, label, branches in rows]))
            if not rows:
                continue
            choices = sorted(local_rows.get(source_key(graph['states'][u]), []))
            if not choices:
                missing.append(u)
                continue
            counts['compared_states'] += 1
            label = choices[0][1]
            old_value = next((v for v, l, _ in rows if l == label), None)
            if label == rows[0][1]:
                continue
            kind = ('no-safe-local-action' if old_value is None else
                    'primary-loss' if old_value[0] != rows[0][0][0] else
                    'secondary-loss' if old_value[1] != rows[0][0][1] else 'equal-value-tie')
            if kind == 'primary-loss': counts['primary_losses'] += 1
            if kind == 'secondary-loss': counts['secondary_losses'] += 1
            if kind == 'equal-value-tie': counts['equal_value_ties'] += 1
            differences.append(dict(state=u, context=graph['states'][u], local_label=label,
                optimal_label=rows[0][1], local_value=old_value, optimal_value=rows[0][0], kind=kind))
        reports[objective] = dict(**counts, differences=differences, missing_local_states=missing,
            unequal_nature_branches=unequal)
        policies[objective] = policy
    return reports, policies


