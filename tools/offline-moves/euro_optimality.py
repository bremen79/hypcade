#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Whole-game Euro/Italian proofs by independent-room additivity.

The original ROM constructs the room queue before play. Surviving inputs only
change the current record; every nonfinal room returns through the same queue
advance. Therefore each record's optimal ranking is independent of room order,
the completed prefix and accidental deaths' changes to the remaining queue.
"""
import argparse
import hashlib
import json
from pathlib import Path

import euro_tables
import rom_proof


class Model:
    def __init__(self, rom, game):
        self.rom, self.game = rom, game
        self.data = euro_tables.inventory(rom, game)
        self.records = {r['id']: r for r in self.data['records']}
        self.records[0] = dict(award=0, death=False, victory=True, inputs=[], default=0)
        # Euro record 648's malformed timeout wraps the original 16-bit record
        # loader into ROM code. Its copied flags mark death. Resolve that actual
        # payload, rather than guessing a replacement destination or omitting it.
        for edge in self.data.get('unresolved_targets', []):
            raw = edge['target'] & 0x7fff
            at = (euro_tables.BASE + (raw - 1) * 32) & 65535
            if at + 32 > len(rom) or not rom[at + 2] & 16:
                raise ValueError('Unclassified out-of-inventory target')
            self.records[raw] = dict(award=0, death=True, victory=False, inputs=[], default=0,
                                     wrapped_address=at, flags=rom[at + 2])

    def record_for(self, state):
        return self.records[state]

    def won(self, state):
        # Zero is a room-dispatch boundary, not a claim of whole-game victory.
        return state == 0 or self.records[state]['victory']

    def actions(self, state):
        record = self.records[state]
        if state < 6 or record['death'] or record['victory']:
            return []
        choices = [(0, record['default'])] + [(i['control'], i['target']) for i in record['inputs']]
        return [((control, 0, target), [target & 0x7fff]) for control, target in choices if target != 65535]

    def graph(self):
        return rom_proof.closure(self, sorted(self.records))

    def verify_room_boundaries(self):
        for root in [self.data['roots'][0], self.data['roots'][1]] + self.data['roots'][3:]:
            seen, pending, terminals = set(), [root], set()
            for state in pending:
                if state in seen:
                    continue
                seen.add(state)
                if self.won(state):
                    terminals.add(state)
                else:
                    for _, targets in self.actions(state):
                        pending.extend(v for v in targets if v not in seen)
            if terminals != ({704} if root == self.data['roots'][1] else {0}):
                raise ValueError('Room exit can change the global continuation')
            record = self.records[root]
            if record['award'] or record['inputs'] or record['default'] != root + 1:
                raise ValueError('Queue entry prelude affects the objective')

    def totals(self, graph, result, queue):
        """Exact remaining-room sum, conditional on the original ROM's queue."""
        index = {v: i for i, v in enumerate(graph['states'])}
        roots = [self.data['roots'][0], *queue, self.data['roots'][1]]
        return dict(minimum_commands=sum(result['fewest'][index[r]] for r in roots),
                    maximum_score=sum(result['highest_score'][index[r]] for r in roots))

    def italian_pools(self):
        if self.game != 'lair_ita':
            raise ValueError('Not the Italian scheduler')
        # 1BBD copies these four independent pools and slot-index lists.
        # 1C34 only swaps entries within each ROM-specified shuffle range.
        # 1C07 resolves offsets, optionally selecting the second paired root.
        # Initial A13E=A01A (0947) selects 12 queue entries. Death at 109E
        # advances head and boundary once, consuming one of five spare entries.
        starts = list(self.rom[0x0DED:0x0DF9])
        sizes = list(self.rom[0x0DFA:0x0E06])
        if starts != [0, 4, 14, 23, 32, 36, 46, 55, 64, 76, 96, 108] or sizes != [4, 10, 9, 5, 4, 10, 9, 5, 12, 5, 12, 5]:
            raise ValueError('Unknown Italian shuffle groups')
        slots = list(self.rom[0x110B:0x111C])
        if len(set(slots)) != 17:
            raise ValueError('Italian queue repeats a pool position')
        pools = []
        for start, size in zip(starts[:4], sizes[:4]):
            entries = []
            for offset in self.rom[0x10EF + start:0x10EF + start + size]:
                at = 0x0E06 + (offset & 127)
                variants = [euro_tables.word(self.rom, at)]
                if offset & 128:
                    variants.append(euro_tables.word(self.rom, at + 2))
                entries.append(variants)
            pools.append(dict(entries=entries,
                initial_count=sum(start <= slot < start + size for slot in slots[:12]),
                spare_count=sum(start <= slot < start + size for slot in slots[12:])))
        return pools

    def italian_queue_enclosures(self, graph, values):
        """All legal pool subsets, without enumerating their permutations.

        Pool swaps and paired-root choices are overapproximated independently.
        Extremizing allocations are not original-RNG reachability witnesses.
        """
        pools=self.italian_pools();index={s:u for u,s in enumerate(graph['states'])}
        fixed=[self.data['roots'][0],self.data['roots'][1]]
        result={}
        for objective,fields in (('shortest',('fewest','score_at_fewest')),
                                 ('highest-score',('fewest_at_score','highest_score'))):
            result[objective]={}
            for metric,field in zip(('moves','score'),fields):
                def cost(root):
                    value=values[field][index[root]]
                    if value is None:raise ValueError('Pool entry has no surviving continuation')
                    return value
                extrema={}
                for name,reverse in (('min',False),('max',True)):
                    chosen=[]
                    for pool in pools:
                        # One root per pool position, then distinct positions.
                        entries=[sorted(((cost(root),root) for root in pair),reverse=reverse)[0]
                                 for pair in pool['entries']]
                        chosen.extend(sorted(entries,reverse=reverse)[:pool['initial_count']])
                    extrema[name]=sum(cost(root) for root in fixed)+sum(value for value,_ in chosen)
                    extrema[name+'_allocation']=[root for _,root in chosen]
                result[objective][metric]=extrema
        return dict(objectives=result,active_rooms=sum(p['initial_count'] for p in pools),
            scope='Death-free initial 12-room queue, bridge and dragon included; all pool subsets/paired roots allowed independently. Enclosing bounds only: RNG joint attainment not proven. Each metric has its own extremizing allocation.')


def certify(rom, game):
    model = Model(rom, game)
    model.verify_room_boundaries()
    graph = model.graph()
    values = rom_proof.solve(graph)
    # Highest/fewest rankings here are exact local continuations with an
    # arbitrary constant global suffix; no queue-permutation graph is needed.
    index = {v: i for i, v in enumerate(graph['states'])}
    rows = {str(root): dict(minimum_commands=values['fewest'][index[root]],
                            maximum_score=values['highest_score'][index[root]])
            for root in [6, *model.data['roots'][3:], 670]}
    proof = dict(game=game, rom_sha256=hashlib.sha256(rom).hexdigest(),
        graph=graph, potential=values, room_values=rows,
        policy_property='Every surviving room exit has the same future queue; rankings are optimal for any remaining queue, including after accidental death.')
    if game == 'laireuro':
        proof['whole_game'] = model.totals(graph, values, model.data['roots'][3:])
        proof['scheduler'] = '36-room multiset, reordered by swaps; drawbridge and dragon separate'
    else:
        proof['pools'] = model.italian_pools()
        proof['initial_queue_enclosures'] = model.italian_queue_enclosures(graph,values)
        proof['scheduler'] = '12 selected rooms plus drawbridge/dragon; five spare queue entries used after accidental deaths; exact totals depend on the already constructed queue'
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', choices=euro_tables.LAYOUTS, required=True)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    proof = certify(euro_tables.load(args.rom, args.game), args.game)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proof, separators=(',', ':')) + '\n')
    print(json.dumps({k: v for k, v in proof.items() if k not in ('graph', 'potential', 'room_values', 'pools')}, indent=2))


if __name__ == '__main__':
    main()
