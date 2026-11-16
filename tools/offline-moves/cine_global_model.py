#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""ROM-audited whole-game Cine boundary models; no sampled-route coverage."""
from functools import lru_cache

import rom_tables
import rom_proof


class AceModel:
    game = 'ace'

    def __init__(self, rom, skill, chance_endpoint=None):
        self.rom, self.skill = rom, skill
        self.chance_endpoint = chance_endpoint
        self.skill_number = ('cadet', 'captain', 'ace').index(skill)
        pointer = rom_tables.word(rom, 0x21C5 + 2 * self.skill_number)
        self.queue = []
        while rom[pointer] != 255:
            self.queue.append(rom[pointer] & 127)
            pointer += 1
        if len(set(self.queue)) != len(self.queue):
            raise ValueError('Episode history cannot be dropped: repeated queue entry')
        self.inventory = rom_tables.inventory(rom, 'ace')
        for record in self.inventory['records']:
            outcomes = [record['trailer'][1]] + [w['outcome'] for i in record['inputs'] for w in i['windows']]
            if record['trailer'][4] & 2 and 0x8C in outcomes:
                raise ValueError('Queue rewind requires a history model')

    @lru_cache(None)
    def record(self, scene, step):
        table = rom_tables.word(self.rom, 0x2183 + 2 * scene)
        return rom_tables.decode_record(self.rom, rom_tables.word(self.rom, table + 2 * step), 'ace')

    def record_for(self, state):
        return self.record(state[1], state[2])

    def select(self, episode, cursor, replayed=0):
        at = 0x20A8 + 4 * episode
        pointer = rom_tables.word(self.rom, at)
        flags = self.rom[at + 2]
        count = 2 if flags & 7 and not flags & 8 else 1
        physical = self.rom[pointer:pointer + count]
        if any(not p & 128 for p in physical):
            raise ValueError('Unmodeled physical selector')
        return [(episode, p & 127, 0, cursor, replayed) for p in physical]

    def start(self):
        return 1, 1, 0, 0, 0

    def won(self, state):
        return state[1:3] == (24, 29)

    def targets(self, state, outcome):
        episode, scene, step, cursor, replayed = state
        record = self.record_for(state)
        flags = record['trailer'][4]
        if outcome == 255:
            return []
        if outcome & 128:
            if flags & 2 and outcome == 0x8C:
                raise ValueError('Unexpected rewind')
            if cursor >= len(self.queue):
                raise ValueError('Unmodeled exhausted initial queue')
            return self.select(self.queue[cursor], cursor + 1)
        target = (episode, scene, outcome, cursor, replayed)
        # Distinct queue entries and the rejected rewind condition imply
        # A035.5 is never set, even on a life restart (1E24 clears bit 7 and
        # returns on that entry). Thus 1F14 only writes unused completion bits.
        # 1F57's bounded replay remains relevant and is retained explicitly.
        enabled = self.skill_number != 0 and not replayed
        enabled &= not (self.skill_number == 1 and scene in (12, 13))
        enabled &= not (self.skill_number == 2 and scene in (4, 5))
        if flags & 64 and enabled:
            offset = 2 if flags & 32 else 0
            physical, next_step = record['extension'][offset:offset + 2]
            physical &= 127
            target = episode, physical, next_step, cursor, int(physical != scene)
        return [target]

    def actions(self, state):
        record = self.record_for(state)
        if record['system']:
            raise ValueError('System record entered gameplay model')
        if record['death'] or record['scene_exit']:
            if record['inputs']:
                raise ValueError('Terminal has control alternatives')
            return []
        choices = [((0, 0, record['trailer'][1]), self.targets(state, record['trailer'][1]))]
        for entry in record['inputs']:
            for window in entry['windows']:
                control = entry['control']
                # Unsupported controls still cost one in optimistic proofs.
                label = (control if control is not None else -1,
                         entry['slot'] * 3 + window['window'], window['outcome'])
                choices.append((label, self.targets(state, window['outcome'])))
        return choices

    def coverage_seeds(self):
        """Every decoded step, including retry-only steps, in its context.

        The replay physical-scene closure is computed from ROM extension data.
        Both values of the retained replay flag are included. This deliberately
        covers a superset of accidental-death states, without optimizing deaths.
        """
        steps = {}
        for node in self.inventory['nodes']:
            steps.setdefault(node['scene'], set()).add(node['step'])
        seeds = [self.start()]
        for cursor, episode in enumerate([1] + self.queue):
            physical = {s[1] for s in self.select(episode, cursor)}
            todo = list(physical)
            for scene in todo:
                for step in steps[scene]:
                    record = self.record(scene, step)
                    if record['trailer'][4] & 64:
                        offset = 2 if record['trailer'][4] & 32 else 0
                        following = record['extension'][offset] & 127
                        if following not in physical:
                            physical.add(following)
                            todo.append(following)
            for scene in sorted(physical):
                for step in sorted(steps[scene]):
                    for replayed in (0, 1):
                        seeds.append((episode, scene, step, cursor, replayed))
        return seeds


def write_ace_policy(model, graph, result, objective, path):
    rankings, unequal = rom_proof.ranked(graph, result, objective)
    if unequal:
        raise ValueError('A3 physical variants differ in objective value')
    contexts = {}
    for state, rows in zip(graph['states'], rankings):
        key = state[1], state[2], state[4]
        choices = tuple(row[1] for row in rows)
        if key in contexts and contexts[key] != choices:
            raise ValueError('Logical queue context affects ranking; retain it in policy')
        contexts[key] = choices
    lines = ['HYPCADE_ROM_POLICY_V2']
    for (scene, step, replayed), choices in sorted(contexts.items()):
        for rank, (control, window, outcome) in enumerate(choices):
            lines.append('%d %d %d %d %d %d %d %d %d' %
                         (scene, step, control, window, outcome, rank,
                          model.skill_number, 8, 8 * replayed))
    path.write_text('\n'.join(lines) + '\n')
    return len(lines) - 1


class SaeModel(AceModel):
    game = 'sae'

    def __init__(self, rom, skill, chance_endpoint=None):
        self.rom, self.skill = rom, skill
        self.chance_endpoint = chance_endpoint
        self.skill_number = ('cadet', 'captain', 'ace').index(skill)
        pointer = rom_tables.word(rom, 0x260B + 2 * self.skill_number)
        self.queue = []
        while rom[pointer] != 255:
            self.queue.append(rom[pointer] & 127)
            pointer += 1
        self.inventory = rom_tables.inventory(rom, 'sae')
        self.steps = {}
        for node in self.inventory['nodes']:
            if node['scene']:
                self.steps.setdefault(node['scene'], set()).add(node['step'])

    @lru_cache(None)
    def record(self, scene, step):
        table = rom_tables.word(self.rom, 0x2571 + 2 * scene)
        return rom_tables.decode_record(self.rom, rom_tables.word(self.rom, table + 2 * step), 'sae')

    def variants(self, episode, cursor):
        if not 1 <= episode <= 40:
            raise ValueError('Unmodeled SAE episode')
        at = 0x2413 + 4 * episode
        pointer = rom_tables.word(self.rom, at)
        flags = self.rom[at + 2]
        count = 2 if flags & 7 and not flags & 8 else 1
        return [(episode, p & 127, 0, cursor, 0) for p in self.rom[pointer:pointer + count]]

    def select(self, episode, cursor, replayed=0):
        choices = self.variants(episode, cursor)
        # SAE extends A3's logical episode range into A080, where its initial
        # queue is also stored. Episodes 32..34 therefore start with the
        # corresponding raw queue byte as history, not zero. Preserve this
        # original-ROM alias; their first selection is deterministic.
        if 32 <= episode < 32 + len(self.queue):
            history = self.queue[episode - 32] | 128
            pick = (history & 1) if not history & 12 else (0 if history & 3 == 1 else 1)
            return [choices[pick]]
        return choices

    def won(self, state):
        return state[1:3] == (25, 63)

    def targets(self, state, outcome):
        episode, scene, step, cursor, _ = state
        if outcome == 255:
            return []
        if not outcome & 128:
            return [(episode, scene, outcome, cursor, 0)]
        if self.record_for(state)['trailer'][4] & 2:
            following, next_cursor = outcome & 127, cursor
        else:
            if cursor >= len(self.queue):
                raise ValueError('Unmodeled exhausted SAE queue')
            following, next_cursor = self.queue[cursor], cursor + 1
        choices = self.select(following, next_cursor)
        if following == 40 and self.chance_endpoint is not None:
            return [choices[self.chance_endpoint]]
        return choices

    def actions(self, state):
        if self.record_for(state)['trailer'][4] & (4 | 8 | 32 | 64):
            raise ValueError('Unmodeled SAE replay effect')
        return super().actions(state)

    def coverage_seeds(self):
        """Close logical contexts under every move and accidental queue skip.

        All steps of each physical variant are seeded, including retry-only
        entries. Then prove the initial-selector freshness invariant on the
        overapproximate macro graph *including* high-byte retry checkpoints.
        """
        from sae_optimality import check_fresh_episodes
        macros, index, macro_edges = [(1, 0)], {(1, 0): 0}, []
        for episode, cursor in macros:
            following = set()
            can_skip = False
            for state in self.variants(episode, cursor):
                for step in self.steps[state[1]]:
                    record = self.record(state[1], step)
                    can_skip |= bool(record['trailer'][4] & 1 and record['extension'][-1] & 128)
                    source = episode, state[1], step, cursor, 0
                    for _, destinations in self.actions(source):
                        following.update((s[0], s[3]) for s in destinations if s[0] != episode or s[3] != cursor)
            if can_skip:
                if cursor >= len(self.queue):
                    raise ValueError('Retry may read beyond the initial queue')
                following.add((self.queue[cursor], cursor + 1))
            for target in sorted(following):
                if target not in index:
                    index[target] = len(macros)
                    macros.append(target)
                macro_edges.append((index[(episode, cursor)], index[target], 0))
        check_fresh_episodes([(ep, 0, 0, cursor) for ep, cursor in macros], macro_edges)
        seeds = [self.start()]
        for episode, cursor in macros:
            for state in self.variants(episode, cursor):
                for step in sorted(self.steps[state[1]]):
                    seeds.append((episode, state[1], step, cursor, 0))
                    record = self.record(state[1], step)
                    if record['trailer'][4] & 1:
                        retry = record['extension'][-1]
                        if not retry & 128:
                            # Resolve retry pointers directly, independently of
                            # inferred inventory table boundaries.
                            self.record(state[1], retry)
                            seeds.append((episode, state[1], retry, cursor, 0))
        return seeds


def write_sae_policy(model, graph, result, objective, path):
    rankings, unequal = rom_proof.ranked(graph, result, objective)
    # Episode 40 is a genuine score-valued choice; ranking is checked at each
    # endpoint separately by the caller. Do not invent a probability law here.
    contexts = {}
    for state, rows in zip(graph['states'], rankings):
        key = state[1:3]
        choices = tuple(row[1] for row in rows)
        if key in contexts and contexts[key] != choices:
            raise ValueError('SAE logical queue context affects the policy')
        contexts[key] = choices
    lines = ['HYPCADE_ROM_POLICY_V1']
    for (scene, step), choices in sorted(contexts.items()):
        for rank, (control, window, outcome) in enumerate(choices):
            lines.append('%d %d %d %d %d %d' % (scene, step, control, window, outcome, rank))
    path.write_text('\n'.join(lines) + '\n')
    return len(lines) - 1, len(unequal)
