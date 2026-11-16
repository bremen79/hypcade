#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reachable Ace continuations with real checkpoints and SAE queue aliasing.

Death recovery grows coverage, never the objective graph. Non-aliased SAE
history choices are conservatively retained; their equal continuation values
are checked separately rather than assigning an invented probability law.
"""
import cine_global_model


class Model:
    def __init__(self, rom, game, skill, difficulty=0):
        self.base = (cine_global_model.AceModel if game == 'ace' else cine_global_model.SaeModel)(rom, skill)
        self.game, self.skill, self.difficulty = game, skill, difficulty
        self.checkpoints = skill == 'cadet' if game == 'ace' else difficulty == 0
        self.recoveries = []

    def record_for(self, state):
        return self.base.record_for(state[:5])

    def won(self, state):
        return self.base.won(state[:5])

    def loaded(self, state):
        ep, scene, step, cursor, replayed, checkpoint, alias = state
        record = self.record_for(state)
        if self.checkpoints and record['trailer'][4] & 1:
            checkpoint = record['extension'][-1]
        return ep, scene, step, cursor, replayed, checkpoint, alias

    def start(self):
        return self.loaded((*self.base.start(), 1, 0))

    def queue(self, alias):
        result = self.base.queue[:]
        if self.game == 'sae' and self.skill == 'ace':
            assert result == [26, 27, 28]
            result[2] = 30 if alias else 28
        return result

    def select(self, episode, cursor, replayed, checkpoint, alias):
        if self.game == 'ace':
            states = self.base.select(episode, cursor, replayed)
        else:
            states = self.base.variants(episode, cursor)
            queue = self.queue(alias)
            if 32 <= episode < 32 + len(queue):
                slot = episode - 32
                history = queue[slot] | 128
                pick = (history & 1) if not history & 12 else (0 if history & 3 == 1 else 1)
                states = [states[pick]]
                changed = history | (1 << pick)
                if changed != history:
                    if not (self.skill == 'ace' and slot == 2 and changed == 158):
                        raise ValueError('Unmodeled queue/history mutation')
                    alias = 1
        return [self.loaded((*s, checkpoint, alias)) for s in states]

    def targets(self, state, outcome):
        if outcome == 255:
            return []
        ep, scene, step, cursor, replayed, checkpoint, alias = state
        rec = self.record_for(state)
        if outcome & 128:
            if self.game == 'sae' and rec['trailer'][4] & 2:
                episode, next_cursor = outcome & 127, cursor
            else:
                queue = self.queue(alias)
                if cursor >= len(queue):
                    raise ValueError('Reachable transition exhausts the initial queue')
                episode, next_cursor = queue[cursor], cursor + 1
            return self.select(episode, next_cursor, 0, 1, alias)
        states = self.base.targets(state[:5], outcome)
        if self.game == 'ace' and rec['trailer'][4] & 64:
            enabled = self.skill != 'cadet' and not replayed
            enabled &= not (self.skill == 'captain' and scene in (12, 13))
            enabled &= not (self.skill == 'ace' and scene in (4, 5))
            if enabled:
                checkpoint = states[0][2]  # 1FAA writes the replay entry.
        return [self.loaded((*s, checkpoint, alias)) for s in states]

    def actions(self, state):
        rec = self.record_for(state)
        if rec['death'] or rec['scene_exit']:
            return []
        if rec['system']:
            raise ValueError('System record reached gameplay')
        labels = [(0, 0, rec['trailer'][1])]
        labels += [(entry['control'] if entry['control'] is not None else -1,
                    entry['slot'] * 3 + window['window'], window['outcome'])
                   for entry in rec['inputs'] for window in entry['windows']]
        return [(label, self.targets(state, label[2])) for label in labels]

    def recover(self, state):
        ep, scene, step, cursor, replayed, checkpoint, alias = state
        if checkpoint & 128:
            queue = self.queue(alias)
            if cursor >= len(queue):
                raise ValueError('Reachable recovery exhausts the initial queue')
            return self.select(queue[cursor], cursor + 1, replayed, 1, alias)
        return [self.loaded((ep, scene, checkpoint, cursor, replayed, checkpoint, alias))]

    def coverage_seeds(self, limit=20000):
        nodes = [self.start()]
        seen = set(nodes)
        self.recoveries = []
        for state in nodes:
            if len(nodes) > limit:
                raise ValueError('Recovery abstraction exceeds analyzed budget')
            if self.record_for(state)['death']:
                targets = self.recover(state)
                self.recoveries.append((state, targets))
            else:
                targets = [t for _, ts in self.actions(state) for t in ts]
            for target in targets:
                if target not in seen:
                    seen.add(target)
                    nodes.append(target)
        return nodes
