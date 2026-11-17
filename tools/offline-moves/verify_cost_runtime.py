#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent cost-plus-future value and runtime-bundle checks."""
import hashlib
import json
from pathlib import Path
import argparse
import tempfile
import struct
import zipfile
from dataclasses import asdict
from types import SimpleNamespace

import cine_global_model
import cine_room_optimality
import rom_controls
import cost_runtime
import rom_proof
import rom_tables
import euro_tables
import policy_retention


def check_context_graphs(folder, roms):
    """Authenticate full reward/transition graphs, not only input inventories."""
    import ace_rules
    from sae_continuations import Continuations
    from sae_rules import SaeRules
    from scene_strategies import continuation_graphs
    def serialized(value):
        return json.loads(json.dumps(value))
    rom=rom_tables.load(roms/'ace.zip','ace')
    for skill in ('cadet','captain','ace'):
        model=ace_rules.Model(rom,skill)
        graph,_,_=rom_controls.simplify_controls(model,model.graph())
        proof=json.loads((folder/('ace-'+skill+'-proof.json')).read_text())
        if serialized(graph)!=proof['graph']:
            raise ValueError('A3 context graph differs from original ROM rules: '+skill)
    rom=rom_tables.load(roms/'sae.zip','sae')
    for skill in ('cadet','captain','ace'):
        for difficulty in (0,1):
            baseline=Continuations(SaeRules(rom,skill,difficulty))
            graphs=continuation_graphs(baseline)
            graph=dict(graphs[0],states=[asdict(p) for p in graphs[0]['states']])
            proof=json.loads((folder/('sae-%s-d%d-proof.json'%(skill,difficulty))).read_text())
            if (serialized(graph)!=proof['graph'] or
                    serialized([g['actions'] for g in graphs])!=proof['selector_actions']):
                raise ValueError('SAE context graph differs from original ROM rules: '+skill)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory_records(inventory):
    records={r['address']:r for r in inventory['records']}
    return {(n['scene'],n['step']):records[n['address']] for n in inventory['nodes']}


def check_graph(graph, values):
    if any(label[0] not in cost_runtime.ALLOWED
           for actions in graph['actions'] for label,_ in actions):
        raise ValueError('Forbidden control in policy certificate')
    rom_proof.verify(graph,values)
    if rom_proof.solve(graph)!=values:
        raise ValueError('Certificate differs from independent Bellman solve')


def basic_expected(table):
    proof=table['certificate'];graph=proof['graph'];values=proof['values']
    check_graph(graph,values)
    records=inventory_records(proof['inventory'])
    states={tuple(s) for s in graph['states']}
    seeds={s for s in records if s[1] in (0,1)}
    if not seeds<=states:raise ValueError('ROM entry/retry seed omitted')
    goals=set(graph['goals'])
    for u,state in enumerate(graph['states']):
        if state[0]==128:continue
        record=records[tuple(state)]
        if graph['awards'][u]!=record['award']:
            raise ValueError('Changed ROM reward')
        if (u in goals or record['death'] or record['system'] or
                (record['scene_exit'] and state[0] not in proof['end_bypass'])):
            expected=set()
        else:
            expected={tuple(r['label']) for r in rom_controls.accepted_regions(record)}
            expected.add((0,0,record['trailer'][1]))
        actual={tuple(label) for label,_ in graph['actions'][u]}
        if actual!=expected:raise ValueError('Decoded ROM alternative omitted or changed: '+str(state))
    alternatives={o:[] for o in cost_runtime.OBJECTIVES}
    for objective in alternatives:
        ranked,_=rom_proof.ranked(graph,values,objective)
        for state,rows in zip(graph['states'],ranked):
            for rank,(_,label,_) in enumerate(rows):
                control,window,outcome=label;key=state[0]|state[1]<<7
                alternatives[objective].append(((key,rank),(key,window%3,outcome,control)))
    return cost_runtime.pack('ArcadeRomRule',alternatives)


def same_table(actual,expected):
    for key in ('kind','rules','orders','equivalent_ranked_aliases'):
        if json.loads(json.dumps(expected[key]))!=actual[key]:
            raise ValueError('Missing or changed runtime '+key)


def euro_expected(table):
    proof=table['certificate'];graph=proof['graph'];values=proof['values']
    check_graph(graph,values)
    records={r['id']:r for r in proof['inventory']['records']}
    index={s:u for u,s in enumerate(graph['states'])};goals=set(graph['goals'])
    if not (set(records)|{0})<=set(index):raise ValueError('European record omitted')
    for state,record in records.items():
        u=index[state]
        expected=set() if state<6 or record['death'] or record['victory'] else {
            (control,0,target) for control,target in [(0,record['default'])]+
            [(r['control'],r['target']) for r in record['inputs']] if target!=65535}
        if {tuple(label) for label,_ in graph['actions'][u]}!=expected:
            raise ValueError('European ROM alternative omitted')
        if graph['awards'][u]!=record['award']:raise ValueError('European reward changed')
    roots=proof['inventory']['roots']
    for root in [roots[0],roots[1],*roots[3:]]:
        record=records[root]
        if record['award'] or record['inputs'] or record['default']!=root+1:
            raise ValueError('European queue prelude changes the objective')
        todo=[index[root]];seen=set(todo);terminals=set()
        for u in todo:
            if u in goals:terminals.add(graph['states'][u])
            for _,targets in graph['actions'][u]:
                for v in targets:
                    if v not in seen:seen.add(v);todo.append(v)
        if terminals!=({704} if root==roots[1] else {0}):
            raise ValueError('European room changes its queue continuation')
    alternatives={o:[] for o in cost_runtime.OBJECTIVES}
    for objective in alternatives:
        ranked,_=rom_proof.ranked(graph,values,objective)
        for state,rows in zip(graph['states'],ranked):
            for rank,(_,label,_) in enumerate(rows):
                alternatives[objective].append(((state,rank),(state,label[2],label[0])))
    return cost_runtime.pack('ArcadeEuroRule',alternatives)


def verify_bundle(folder, include=None, roms=None, euro_include=None):
    folder=Path(folder);manifest=json.loads((folder/'manifest.json').read_text())
    if manifest['schema']!=7 or manifest['runtime_timing']!='live-rom':
        raise ValueError('Expected the cost-plus-future live-ROM bundle')
    if manifest.get('sources')!=cost_runtime.source_identity():
        raise ValueError('Policy generator/proof source changed; regenerate the bundle')
    for name,expected in manifest['files'].items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts:raise ValueError('Bundle path escapes its root')
        if digest(folder/path)!=expected:raise ValueError('Changed bundle input: '+name)
    tables={game:json.loads((folder/(game+'.json')).read_text())
            for game in (*cine_room_optimality.GAMES,'ace','sae',*euro_tables.LAYOUTS)}
    for game in cine_room_optimality.GAMES:
        same_table(tables[game],basic_expected(tables[game]))
        if roms:
            rom=rom_tables.load(roms/(game+'.zip'),game)
            if rom_tables.inventory(rom,game)!=tables[game]['certificate']['inventory']:
                raise ValueError('Inventory differs from original ROM: '+game)
            same_table(tables[game],cost_runtime.dl1_tables(rom,game))
    for game in euro_tables.LAYOUTS:
        same_table(tables[game],euro_expected(tables[game]))
        if roms:
            rom=euro_tables.load(roms/(game+'.zip'),game)
            same_table(tables[game],cost_runtime.euro_table(rom,game))
    proof_dir=folder/'proofs'
    with tempfile.TemporaryDirectory(prefix='hypcade-cost-proof-') as temporary:
        temporary=Path(temporary)
        for skill in ('cadet','captain','ace'):
            proof=json.loads((proof_dir/('ace-'+skill+'-proof.json')).read_text())
            check_graph(proof['graph'],proof['values'])
            for objective in cost_runtime.OBJECTIVES:
                cine_global_model.write_ace_policy(SimpleNamespace(skill_number=('cadet','captain','ace').index(skill)),
                    proof['graph'],proof['values'],objective,temporary/(skill+'-'+objective+'.policy'))
        same_table(tables['ace'],cost_runtime.ace_tables(temporary))
    inventory=json.loads((proof_dir/'sae-inventory.json').read_text())
    records=inventory_records(inventory);groups={}
    for skill in ('cadet','captain','ace'):
        for difficulty in (0,1):
            proof=json.loads((proof_dir/('sae-%s-d%d-proof.json'%(skill,difficulty))).read_text())
            graph=proof['graph'];baseline={}
            for bit in (0,1):
                selected=dict(graph,actions=proof['selector_actions'][bit])
                check_graph(selected,proof['values'][bit])
                for objective in cost_runtime.OBJECTIVES:
                    ranked,_=rom_proof.ranked(selected,proof['values'][bit],objective)
                    for u,rows in enumerate(ranked):
                        if not rows:continue
                        point=graph['states'][u];scene,step=point['scene'],point['step']
                        state=scene|step<<7;gate=int(point['score_suppressed'])
                        context=3|(2<<2)|(gate<<4);record=records[scene,step]
                        result=[]
                        for _,label,_ in rows:
                            control,which,outcome=label;slot,window=divmod(which,3)
                            if control:
                                entry=record['inputs'][slot]
                                if entry['control']!=control or entry['windows'][window]['outcome']!=outcome:
                                    raise ValueError('Rule does not identify its ROM descriptor')
                                header=entry['header']
                            else:slot=window=header=0
                            result.append((state,context,slot,window,header,outcome,control))
                        key=state,gate,objective
                        if key in groups and groups[key]!=result:
                            raise ValueError('Runtime key drops a necessary policy context')
                        groups[key]=result
                        if bit==0:baseline[objective,u]=result
                        elif baseline.get((objective,u))!=result:
                            raise ValueError('Selector changes the best action ranking')
    alternatives={o:[] for o in cost_runtime.OBJECTIVES}
    for (state,gate,objective),rows in groups.items():
        for rank,row in enumerate(rows):alternatives[objective].append(((state,row[1],rank),row))
    expected=cost_runtime.pack('ArcadeCostRule',alternatives)
    # Alias counts describe source serialization, not semantic coverage.
    expected['equivalent_ranked_aliases']=tables['sae']['equivalent_ranked_aliases']
    same_table(tables['sae'],expected)
    for game, table in tables.items():
        if table.get('retention') != policy_retention.decide(game, table, proof_dir):
            raise ValueError('Incorrect retained policies: '+game)
    catalog = policy_retention.java_catalog(tables)
    if (folder/'MovePolicyCatalog.java').read_text() != catalog:
        raise ValueError('UI policy catalog differs from retained strategies')
    if include and (cost_runtime.REPO/'android/app/src/main/java/org/hypseus/android/MovePolicyCatalog.java').read_text() != catalog:
        raise ValueError('Launcher policy catalog differs from packaged strategies')
    source=cost_runtime.include(tables)
    if source!=(folder/'arcade_moves.inc').read_text():raise ValueError('Compiled bundle omits policy rows')
    if include and source!=Path(include).read_text():raise ValueError('APK include differs from verified bundle')
    source=cost_runtime.euro_include(tables)
    if source!=(folder/'arcade_euro_moves.inc').read_text():raise ValueError('European include omits ranked rules')
    if euro_include and source!=Path(euro_include).read_text():raise ValueError('APK European include differs')
    if roms:
        for game in ('ace','sae'):
            rom=rom_tables.load(roms/(game+'.zip'),game)
            if rom_tables.inventory(rom,game)!=json.loads((proof_dir/(game+'-inventory.json')).read_text()):
                raise ValueError('Context inventory differs from original ROM: '+game)
        check_context_graphs(proof_dir,roms)
    return dict(games=9,european_games=2,all_ranked_alternatives=True,live_rom_timing=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle-dir',type=Path)
    parser.add_argument('--roms',type=Path)
    parser.add_argument('--apk',type=Path,action='append',default=[])
    args=parser.parse_args();root=Path(__file__).resolve().parents[2]
    folder=args.bundle_dir or root/'android/moves/strategies'
    result=verify_bundle(folder,None if args.bundle_dir else root/'android/app/jni/arcade_moves.inc',args.roms,
                         None if args.bundle_dir else root/'android/app/jni/arcade_euro_moves.inc')
    tables=[policy_retention.runtime_table(json.loads(p.read_text()))
            for p in sorted(folder.glob('*.json')) if p.name!='manifest.json']
    for apk in args.apk:
        with zipfile.ZipFile(apk) as archive:
            libraries=[n for n in archive.namelist() if n.endswith('/libmain.so')]
            if not libraries:raise ValueError('APK has no native engine')
            for name in libraries:
                blob=archive.read(name)
                for table in tables:
                    layout={'ArcadeCostRule':'<HBBBBBB','ArcadeRomRule':'<HBBBx','ArcadeEuroRule':'<HHBx'}[table['kind']]
                    if b''.join(struct.pack(layout,*row) for row in table['rules']) not in blob:
                        raise ValueError('APK omits a cost-plus-future rule pool')
                    for order in table['orders'].values():
                        if struct.pack('<'+'H'*len(order),*order) not in blob:
                            raise ValueError('APK omits a ranked strategy')
    print('Cost + future: %d Cine and %d European ROMs; complete ranked policies, '
          'independent Bellman certificates, live ROM timing passed'%(result['games'],result['european_games']))


def verify_saved_values(folder):
    """Check the actual saved local/exit costs, streaming one context at a time."""
    manifest = json.loads((folder / 'manifest.json').read_text())
    if manifest['runtime_timing'] != 'live-rom':
        raise ValueError('Candidate must use live ROM timing')
    for name, expected in manifest['files'].items():
        if digest(folder / name) != expected:
            raise ValueError('Candidate file checksum differs: ' + name)
    contexts = branches = 0
    for case in manifest['cases']:
        path = folder / ('%s-d%d-values.jsonl' % (case['skill'], case['difficulty']))
        count = 0
        with path.open() as stream:
            next(stream)  # schema/setting header
            for line in stream:
                row = json.loads(line)
                count += 1
                for phase in row['phases']:
                    for objective, alternatives in phase['policies'].items():
                        for alternative in alternatives:
                            for part in alternative['branches']:
                                if part is None:
                                    continue
                                for suffix in ('inputs', 'score'):
                                    if part['remaining_' + suffix] != part['local_' + suffix] + part['exit_' + suffix]:
                                        raise ValueError('Saved local/exit cost does not add up')
                                if alternative['rank'] == 0:
                                    inputs = 'fewest' if objective == 'shortest' else 'fewest_at_score'
                                    score = 'score_at_fewest' if objective == 'shortest' else 'highest_score'
                                    if (part['remaining_inputs'], part['remaining_score']) != (phase['values'][inputs], phase['values'][score]):
                                        raise ValueError('Chosen saved exit differs from solved value')
                                branches += 1
        if count != case['states']:
            raise ValueError('Saved scene contexts are incomplete')
        contexts += count
    return dict(contexts=contexts, branch_decompositions=branches, timing='live-rom')


if __name__=='__main__':main()


