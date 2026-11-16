#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile cost-plus-future rankings; keep every timing value in the live ROM.

A3 and SAE consume their independently checked scene/exit-cost exports.
DL1 emits per-exit rankings after checking that a common continuation offset
cancels; its whole-game scheduler/attainment proofs are verified separately.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import cine_room_optimality
import rom_controls
import dl1_exit_strategies
import move_arrays
import rom_proof
import rom_tables
import euro_optimality
import euro_tables as euro_rom

OBJECTIVES = ('highest-score', 'shortest')
ALLOWED = {0, 1, 2, 4, 8, 16}
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
SOURCES = ('cost_runtime.py','scene_strategies.py','ace_scene_strategies.py',
           'rom_tables.py','rom_proof.py','dl1_exit_strategies.py','cine_room_optimality.py',
           'cine_global_model.py','cine_recovery_model.py','ace_rules.py','sae_rules.py',
           'sae_continuations.py','rom_rules.py','rom_controls.py','move_arrays.py',
           'euro_optimality.py','euro_tables.py')


def source_identity():
    paths=[ROOT/n for n in SOURCES]
    paths.extend(REPO/'android/app/jni'/n for n in ('arcade_move_policy.h','arcade_move_catalog.h','arcade_euro_policy.h'))
    return {str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def pack(kind, alternatives):
    pool = sorted({row for rows in alternatives.values() for _, row in rows})
    if len(pool) > 65536 or any(row[-1] not in ALLOWED for row in pool):
        raise ValueError('Invalid runtime rule pool')
    index = {row: i for i, row in enumerate(pool)}
    orders = {objective: list(dict.fromkeys(index[row] for _, row in sorted(rows, key=lambda x: x[0])))
              for objective, rows in alternatives.items()}
    return dict(kind=kind, rules=pool, orders=orders,
                equivalent_ranked_aliases={o: len(alternatives[o])-len(orders[o]) for o in orders})


def ace_tables(folder):
    alternatives = {o: [] for o in OBJECTIVES}
    for skill in ('cadet', 'captain', 'ace'):
        for objective in OBJECTIVES:
            lines = (folder/(skill+'-'+objective+'.policy')).read_text().splitlines()
            if lines[0] != 'HYPCADE_ROM_POLICY_V2':
                raise ValueError('Expected contextual A3 exit-cost policy')
            for line in lines[1:]:
                scene, step, control, window, outcome, rank, selected, mask, value = map(int, line.split())
                if mask != 8 or value not in (0, 8):
                    raise ValueError('Unmapped A3 context')
                state = scene | step << 7
                context = selected | ((value >> 3) << 2) | (2 << 4)
                row = (state, context, 255, window % 3, 0, outcome, control)
                alternatives[objective].append(((state, context, rank), row))
    return pack('ArcadeCostRule', alternatives)


def sae_tables(folder):
    table = json.loads((folder/'policy.json').read_text())
    if table['timing'] != 'live-rom':
        raise ValueError('SAE policies must use live ROM timing')
    alternatives = {o: [] for o in OBJECTIVES}
    for objective in OBJECTIVES:
        for rank, index in enumerate(table['orders'][objective]):
            state, gate, slot, window, header, outcome, control = table['rules'][index]
            context = 3 | (2 << 2) | (gate << 4)
            row = (state, context, slot, window, header, outcome, control)
            alternatives[objective].append(((state, context, rank), row))
    return pack('ArcadeCostRule', alternatives)


def dl1_tables(rom, game):
    model = cine_room_optimality.Model(rom, game)
    graph, reference, _ = rom_controls.simplify_controls(model, model.graph())
    terminals = {u: ':'.join(map(str, list(model.return_labels)[graph['states'][u][1]]))
                 if graph['states'][u][0] == 128 else 'win' for u in graph['goals']}
    coefficients = dl1_exit_strategies.factor(graph, terminals)
    common = {name: dict.fromkeys(dl1_exit_strategies.FIELDS, 0) for name in coefficients}
    values = dl1_exit_strategies.evaluate(coefficients, common)
    if values != reference:
        raise ValueError('Common future cost changes DL1 ranking')
    alternatives = {o: [] for o in OBJECTIVES}
    for objective in OBJECTIVES:
        ranked, unequal = rom_proof.ranked(graph, values, objective)
        if unequal:
            raise ValueError('Unresolved DL1 scene branch')
        for state, choices in zip(graph['states'], ranked):
            for rank, (_, label, _) in enumerate(choices):
                if state[0] >= 128:
                    raise ValueError('Dispatch boundary has an input recommendation')
                control, window, outcome = label
                key = state[0] | state[1] << 7
                alternatives[objective].append(((key, rank), (key, window % 3, outcome, control)))
    table = pack('ArcadeRomRule', alternatives)
    table['certificate'] = dict(graph=graph,values=values,
        end_bypass=sorted(model.end_bypass),terminals=terminals,inventory=model.inventory)
    return table


def euro_table(rom,game):
    model=euro_optimality.Model(rom,game);model.verify_room_boundaries()
    graph=model.graph();values=rom_proof.solve(graph)
    alternatives={o:[] for o in OBJECTIVES}
    for objective in OBJECTIVES:
        ranked,_=rom_proof.ranked(graph,values,objective)
        for state,rows in zip(graph['states'],ranked):
            for rank,(_,label,_) in enumerate(rows):
                alternatives[objective].append(((state,rank),(state,label[2],label[0])))
    table=pack('ArcadeEuroRule',alternatives)
    table['certificate']=dict(graph=graph,values=values,inventory=model.data,
        room_queue_independent=True,per_player_difficulty=euro_rom.LAYOUTS[game]['per_player_difficulty'])
    return table


def include(tables):
    lines = ['// SPDX-License-Identifier: GPL-3.0-or-later',
             '// Generated by cost_runtime.py; cost + future, live ROM timing only.']
    for game, table in sorted(tables.items()):
        if table['kind']=='ArcadeEuroRule':continue
        lines.append('static const %s %s_rules[] = {' % (table['kind'], game))
        lines.extend('    {'+', '.join(map(str, row))+'},' for row in table['rules'])
        lines.append('};')
        for objective, suffix in [('highest-score', 'max'), ('shortest', 'fewest')]:
            order = table['orders'][objective]
            lines.append('static const uint16_t %s_rules_%s[] = {' % (game, suffix))
            lines.extend('    '+', '.join(map(str, order[i:i+16]))+',' for i in range(0, len(order), 16))
            lines.append('};')
    lines.append('static const ArcadeCineProfile arcade_cine_profiles[] = {')
    for game, table in sorted(tables.items()):
        if table['kind']=='ArcadeEuroRule':continue
        macro = 'ARCADE_COST_PROFILE' if table['kind'] == 'ArcadeCostRule' else 'ARCADE_CINE_PROFILE'
        lines.append('    %s("%s", %s),' % (macro, game, game))
    lines.append('};')
    return move_arrays.deduplicate('\n'.join(lines)+'\n')[0]


def euro_include(tables):
    lines=['// SPDX-License-Identifier: GPL-3.0-or-later',
           '// Generated by cost_runtime.py; common queue continuation costs.']
    euro={g:t for g,t in tables.items() if t['kind']=='ArcadeEuroRule'}
    for game,table in sorted(euro.items()):
        lines.append('static const ArcadeEuroRule %s_rules[] = {'%game)
        lines.extend('    {'+', '.join(map(str,row))+'},' for row in table['rules']);lines.append('};')
        for objective,suffix in [('highest-score','max'),('shortest','fewest')]:
            order=table['orders'][objective];lines.append('static const uint16_t %s_rules_%s[] = {'%(game,suffix))
            lines.extend('    '+', '.join(map(str,order[i:i+16]))+',' for i in range(0,len(order),16));lines.append('};')
    lines.append('static const ArcadeEuroProfile arcade_euro_profiles[] = {')
    for game,table in sorted(euro.items()):
        lines.append('    ARCADE_EURO_PROFILE("%s", %s, %s),'%(game,game,
            'true' if table['certificate']['per_player_difficulty'] else 'false'))
    lines.append('};')
    return move_arrays.deduplicate('\n'.join(lines)+'\n')[0]


def generate(roms, ace, sae, output):
    output.mkdir(parents=True, exist_ok=True)
    tables = {game: dl1_tables(rom_tables.load(roms/(game+'.zip'), game), game)
              for game in cine_room_optimality.GAMES}
    tables.update(ace=ace_tables(ace), sae=sae_tables(sae))
    tables.update({game:euro_table(euro_rom.load(roms/(game+'.zip'),game),game) for game in euro_rom.LAYOUTS})
    proofs = output/'proofs'
    proofs.mkdir(exist_ok=True)
    for game, folder in [('ace', ace), ('sae', sae)]:
        data=json.loads((folder/'inventory.json').read_text())
        (proofs/(game+'-inventory.json')).write_text(json.dumps(data,separators=(',',':'))+'\n')
        for path in sorted(folder.glob('*-proof.json')):
            (proofs/(game+'-'+path.name)).write_text(json.dumps(json.loads(path.read_text()),separators=(',',':'))+'\n')
    for game, table in tables.items():
        (output/(game+'.json')).write_text(json.dumps(table, separators=(',', ':'))+'\n')
    source = include(tables)
    (output/'arcade_moves.inc').write_text(source)
    (output/'arcade_euro_moves.inc').write_text(euro_include(tables))
    sizes = {game: (8 if table['kind'] == 'ArcadeCostRule' else 6)*len(table['rules'])+
             2*sum(map(len, table['orders'].values())) for game, table in tables.items()}
    (output/'manifest.json').write_text(json.dumps(dict(schema=6, runtime_timing='live-rom',
        method='local scene cost plus exit continuation', runtime_bytes=sizes,sources=source_identity(),
        files={str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*')
               if p.is_file() and p.name != 'manifest.json'}), indent=2)+'\n')
    print('Compiled', len(tables), 'ROM profiles;', sum(sizes.values()), 'runtime bytes before array sharing')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--roms', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import ace_scene_strategies
    import scene_strategies
    work=REPO/'local-tools';work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cost-strategies-',dir=work) as temporary:
        temporary=Path(temporary)
        ace_scene_strategies.generate(args.roms/'ace.zip',temporary/'ace')
        scene_strategies.generate(args.roms/'sae.zip',temporary/'sae')
        generate(args.roms,temporary/'ace',temporary/'sae',args.output)


if __name__ == '__main__':
    main()
