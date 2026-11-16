#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Raw-hard US DL1 support costs conditioned through all three room passes.

Two ordered optional-resource streams share one 32-way lap boundary. Per-group
history is eliminated locally; actual observations constrain roots, history
bits and consumed optional flags. Refresh phases remain relaxed support, not
an expectation or a promise of physical controllability.
"""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

from functools import lru_cache

from dl1_allocation import add


def allocate(groups, table, costs, known=None, offset=40, boundaries=range(32)):
    known = {} if known is None else known
    if any(c >= 3 or used for (c, _, used), _ in table[0, 0]):
        raise ValueError('Raw-hard first visit must not inject optional rooms')

    @lru_cache(None)
    def choices(lap, group, used, mask):
        observed = known.get((lap, group))
        rows = []
        for (choice, after_mask, after_used), phase in table[used, mask]:
            root = groups[group][choice]+offset if choice < 3 else 80+choice-3
            if observed is not None and (root, after_mask, after_used) != (
                    observed['scene'], observed['mask'], observed['used']):
                continue
            rows.append((choice, after_mask, after_used, phase, root))
        return rows

    best = None
    count = peak = 0
    for boundary in boundaries:
        states = {(0, boundary): ((0, 0), ())}
        for g in range(len(groups)):
            following = {}
            for (used2, used3), (value, witness) in states.items():
                for first, mask1, used1, phase1, root1 in choices(0, g, 0, 0):
                    if used1:
                        raise ValueError('First visit consumed a shared optional resource')
                    for second, mask2, next2, phase2, root2 in choices(1, g, used2, mask1):
                        if next2 & ~boundary:
                            continue
                        for third, mask3, next3, phase3, root3 in choices(2, g, used3, mask2):
                            candidate = add(value, costs[root1], costs[root2], costs[root3])
                            key = next2, next3
                            if key not in following or candidate < following[key][0]:
                                row = dict(group=g+1, first=first, second=second, third=third,
                                    roots=[root1, root2, root3], phase1=phase1, phase2=phase2, phase3=phase3,
                                    mask_after_first=mask1, mask_after_second=mask2, mask_after_third=mask3)
                                following[key] = candidate, witness+(row,)
            states = following
            count += len(states)
            peak = max(peak, len(states))
            if not states:
                break
        for (used2, used3), (value, witness) in states.items():
            if used2 == boundary and (best is None or value < best['value']):
                best = dict(value=value, boundary1=0, boundary=boundary, final_used=used3, groups=witness)
    if best is None:
        raise ValueError('No selector-support allocation is compatible with the observations')
    best.update(total_dp_states=count, peak_dp_states=peak)
    return best


def observations(rows, groups, final, offset=40):
    """Collapse record entries to room loads; validate all monotone resources."""
    result = []
    previous_group = None
    masks = [0]*13
    used = 0
    for row in rows:
        if row['type'] != 'late_entry' or row['group'] == previous_group:
            continue
        previous_group = row['group']
        lap, g = divmod(len(result), 13)
        if lap >= 3 or previous_group != g+1:
            raise ValueError('Room observations do not follow three ordered thirteen-group passes')
        scene, mask = row['scene'], row['mask'] & 7
        if g == 12:
            if scene != final[lap]+offset or mask != (4, 6, 7)[lap]:
                raise ValueError('Final group differs from the descending ROM order')
        elif 80 <= scene <= 84:
            bit = 1 << (scene-80)
            if used & bit or mask != masks[g]:
                raise ValueError('Optional-room resource or ordinary history is not monotone')
            used |= bit
        else:
            changed = mask ^ masks[g]
            if not changed or changed & (changed-1) or masks[g] & changed:
                raise ValueError('Regular room did not consume one new history bit')
            if scene != groups[g][changed.bit_length()-1]+offset:
                raise ValueError('Physical room and actual consumed variant disagree')
        masks[g] = mask
        result.append(dict(lap=lap, group=g+1, scene=scene, mask=mask, used=used))
    if len(result) != 39:
        raise ValueError('Incomplete room-load observations')
    return result
