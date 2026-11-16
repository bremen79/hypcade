#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Complete DL1 per-exit certificates and ROM-derived additive reductions."""
import argparse
import collections
import hashlib
import json
from pathlib import Path

import rom_proof
import rom_tables

GAMES = ('dle21', 'lair_a', 'lair_b', 'lair_c', 'lair_d', 'lair_e', 'lair_f')


class Model:
    def __init__(self, rom, game):
        self.rom, self.game = rom, game
        self.spec = rom_tables.LAYOUTS[game]
        self.inventory = rom_tables.inventory(rom, game)
        self.cache = {}
        final_step = 15 if game == 'dle21' else 13
        winner = self.record(36, final_step)
        harder_offset = 51 if game == 'dle21' else 42 if game in ('lair_e', 'lair_f') else 40
        harder_winner = self.record(36 + harder_offset, final_step)
        winning_frames = {tuple(winner['trailer'][5:7]), tuple(harder_winner['trailer'][5:7])}
        self.winning_addresses = {r['address'] for r in self.inventory['records']
            if r['scene_exit'] and r['trailer'][0] & 15 == 15 and
               tuple(r['trailer'][5:7]) in winning_frames}
        # Original main loop deliberately bypasses the generic end flag on
        # these intermission records. Other end records are game-over paths.
        self.end_bypass = (40, 91) if game == 'dle21' else (20, 62) if game in ('lair_e', 'lair_f') else (20, 60)
        self.return_labels = {}

    def record(self, scene, step):
        key = scene, step
        if key not in self.cache:
            table = rom_tables.word(self.rom, self.spec['roots'] + 2 * scene)
            self.cache[key] = rom_tables.decode_record(self.rom, rom_tables.word(self.rom, table + 2 * step), self.game)
        return self.cache[key]

    def record_for(self, state):
        if state[0] == 128:
            return dict(award=0, death=False)
        return self.record(*state)

    def won(self, state):
        return state[0] == 128 or self.record(*state)['address'] in self.winning_addresses

    def actions(self, state):
        if self.won(state):
            return []
        scene, step = state
        record = self.record(scene, step)
        if record['death'] or record['system'] or (record['scene_exit'] and scene not in self.end_bypass):
            return []
        choices = [((0, 0, record['trailer'][1]), record['trailer'][1])]
        for entry in record['inputs']:
            for window in entry['windows']:
                label = (entry['control'] if entry['control'] is not None else -1,
                         entry['slot'] * 3 + window['window'], window['outcome'])
                if window['outcome'] != 255:
                    choices.append((label, window['outcome']))
        result = []
        for label, outcome in choices:
            if outcome & 128:
                effect = ('explicit', outcome & 127) if record['trailer'][4] & 2 else ('next',)
                if effect not in self.return_labels:
                    self.return_labels[effect] = len(self.return_labels)
                target = 128, self.return_labels[effect]
            else:
                target = scene, outcome
            result.append((label, [target]))
        return result

    def graph(self):
        # Cine pointer tables overlap. Treating every inferred table suffix as
        # an entry manufactures impossible scene/step combinations and bogus
        # positive-score cycles. Original selection starts at step 0; life
        # restart uses step 1. Close both through EVERY decoded control and
        # timeout instead of seeding arbitrary cross-table aliases.
        seeds = [(n['scene'], n['step']) for n in self.inventory['nodes'] if n['step'] in (0, 1)]
        return rom_proof.closure(self, seeds)


def certify(rom, game):
    model = Model(rom, game)
    graph = model.graph()
    values = rom_proof.solve(graph)
    index = {s: i for i, s in enumerate(graph['states'])}
    roots = {}
    for scene in range(model.spec['count']):
        if (scene, 0) in index:
            u = index[scene, 0]
            roots[scene] = dict(minimum_commands=values['fewest'][u], maximum_score=values['highest_score'][u])
    proof = dict(game=game, rom_sha256=hashlib.sha256(rom).hexdigest(), graph=graph,
        potential=values, roots=roots, return_labels=[list(k) for k in model.return_labels],
        whole_game_proven=False, continuation_scope='Complete surviving continuations to each room-dispatch boundary; no planned deaths')
    if game == 'dle21':
        # Authored chapters loop their three choice groups until each variant
        # has occurred. The two zero-input intermissions return twice, then
        # advance. The three final chapter choices have the same nine-room
        # multiset, with the dragon fixed last in each arrangement.
        chapters = []
        for start in (12, 16, 20):
            chapter = []
            for episode in range(start, start + 3):
                at = 0x2203 + 4 * episode
                pointer = rom_tables.word(rom, at)
                if rom[at + 2:at + 4] != bytes((10, 7)):
                    raise ValueError('Final chapter no longer uses fixed three-variant order')
                chapter.extend(x & 127 for x in rom[pointer:pointer + 3])
            chapters.append(chapter)
        if not all(collections.Counter(c) == collections.Counter(chapters[0]) for c in chapters):
            raise ValueError('DLE21 chapter choices are not objective-equivalent permutations')
        compulsory = [0, 50, 1, 15, 26, 8, 12, 22, 2, 11, 30,
                      7, 3, 23, 9, 5, 13, 24, 17, 28, 20, *chapters[0]]
        proof['chapter_multisets'] = chapters
        proof['compulsory_scene_multiset'] = compulsory
        proof['root_bounds'] = dict(
            minimum_commands=sum(roots[s]['minimum_commands'] for s in compulsory),
            maximum_score=sum(roots[s]['maximum_score'] for s in compulsory))
        proof['scheduler_reduction'] = 'Two complete three-variant chapters followed by any permutation of the same final nine rooms; intermissions have zero objective value'
    elif game in ('lair_e', 'lair_f'):
        signature = bytes.fromhex('3a 54 a0 cb 27 cb 27')
        at = rom.find(signature)
        if at < 3 or rom[at - 3] != 0x21:
            raise ValueError('Missing logical descriptor table reference')
        descriptors = rom_tables.word(rom, at - 2)
        groups = []
        for episode in range(1, 14):
            at = descriptors + 4 * episode
            pointer = rom_tables.word(rom, at)
            if rom[at + 2:at + 4] != bytes((10 if episode == 13 else 2, 7)):
                raise ValueError('Unknown three-variant descriptor')
            groups.append([x & 127 for x in rom[pointer:pointer + 3]])
        compulsory = [s for group in groups for s in group]
        proof['groups'] = groups
        proof['compulsory_scene_multiset'] = compulsory
        hard_moves = sum(roots[s + 42]['minimum_commands'] for s in compulsory)
        hard_score = sum(roots[s + 42]['maximum_score'] for s in compulsory)
        difficulty_values = []
        for difficulty, normal_groups in enumerate((0, 0, 4, 8)):
            move_choices, score_choices = [], []
            for group in groups[:normal_groups]:
                move_choices.append([roots[s]['minimum_commands'] - roots[s + 42]['minimum_commands'] for s in group])
                score_choices.append([roots[s]['maximum_score'] - roots[s + 42]['maximum_score'] for s in group])
            difficulty_values.append(dict(difficulty=difficulty,
                normal_groups=normal_groups,
                minimum_commands_range=[hard_moves + sum(min(v) for v in move_choices), hard_moves + sum(max(v) for v in move_choices)],
                maximum_score_range=[hard_score + sum(min(v) for v in score_choices), hard_score + sum(max(v) for v in score_choices)],
                per_group_command_adjustments=move_choices, per_group_score_adjustments=score_choices))
        proof['difficulty_values'] = difficulty_values
        proof['scheduler_reduction'] = 'All three variants of each group occur; the first 0/0/4/8 groups may use a normal version once before progress selects harder versions. Preserve those version costs rather than treating the two sets as mirrors. Supported bank settings disable the optional-room injector.'
    else:
        proof['scheduler_reduction'] = 'Optional-room injector enabled; exact room multiset depends on ROM refresh choices. Requires separate injector proof before claiming whole-game optimum.'
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', choices=GAMES, required=True)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    proof = certify(rom_tables.load(args.rom, args.game), args.game)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proof, separators=(',', ':')) + '\n')
    print(args.game, len(proof['graph']['states']), proof.get('root_bounds', proof['scheduler_reduction']))


if __name__ == '__main__':
    main()
