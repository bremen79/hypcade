#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Package complete ROM policies, with replay-derived timing calibrations.

Successful plays calibrate timing; they never define the coverage boundary.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import moves as move_tools
import score_routes
import export_rom_moves


def ranked_rows(candidates, policy):
    """Use all proven branches, retaining this objective's choice to act or wait.

    A route's objective is not a coverage boundary. Missing calibration is
    permitted: complete ROM policies supply continuations independently of
    which branches were replayed.
    Do not copy the other policy blindly: a missing action can mean deliberate
    waiting (for example, declining to energize in Space Ace).
    """
    best={tuple(c['source']):c for c in policy['choices'] if c['rank']==0}
    items={}
    for row,remaining in candidates:
        state,frame,timing,outcome,control=row
        choice=best.get((state&127,(state>>7)&127))
        if choice is None:raise ValueError('Verified runtime state absent from ROM policy')
        if (choice['control'],choice['window']%3,choice['outcome']) != (control,(timing>>8)%3,outcome):
            continue
        rank=remaining if policy['objective']=='shortest' else (-remaining[1],remaining[0])
        items[row]=min(items.get(row,rank),rank)
    return items


def runtime_policy(rules):
    """Compile all ranked ROM choices, retaining waits and tied alternatives."""
    native=sorted({(r['source'][0]|(r['source'][1]<<7),r['window'] or 0,
                    r['outcome'],r['control']) for r in rules if r['objectives']})
    if len(native)>65536:raise ValueError('ROM rule pool exceeds 16-bit indices')
    indices={r:i for i,r in enumerate(native)}
    orders={}
    for objective in export_rom_moves.OBJECTIVES:
        ranked=sorted((r for r in rules if objective in r['objectives']),
                      key=lambda r:(r['source'][0]|(r['source'][1]<<7),r['objectives'][objective]['rank']))
        orders[objective]=list(dict.fromkeys(indices[(r['source'][0]|(r['source'][1]<<7),
                              r['window'] or 0,r['outcome'],r['control'])] for r in ranked))
    return native,orders


def rule_coverage(inventory,rules,native,orders):
    """Account for every ROM rule and reject missing playable continuations."""
    policies={o:export_rom_moves.rom_tables.policies(inventory,o) for o in export_rom_moves.OBJECTIVES}
    expected=export_rom_moves.compile_rules(inventory,policies)
    if rules!=expected:raise ValueError('Missing or changed decoded ROM rule')
    expected_native,expected_orders=runtime_policy(expected)
    if native!=expected_native or orders!=expected_orders:
        raise ValueError('Missing ranked ROM alternative in runtime policy')
    records={r['address']:r for r in inventory['records']}
    nodes={(n['scene'],n['step']):records[n['address']] for n in inventory['nodes']}
    # Independent reverse reachability: an unranked playable path must fail,
    # rather than silently disappearing because the local planner missed it.
    safe={k for k,r in nodes.items() if r['scene_exit'] and not r['death'] and not r['system']}
    while True:
        before=len(safe)
        for edge in inventory['edges']:
            target=tuple(edge['target'])
            if not nodes[target]['death'] and (edge['outcome']&128 or target in safe):
                safe.add(tuple(edge['source']))
        if len(safe)==before:break
    dispositions=Counter()
    for rule in rules:
        if rule['objectives']:reason='runtime-policy'
        elif rule['classification']=='candidate':
            if rule['dispatch'] or tuple(rule['target']) in safe:
                raise ValueError('Unranked playable ROM rule: '+rule['id'])
            reason='no-safe-local-completion'
        elif rule['classification']=='unsupported-control':
            if rule['target'] and (rule['dispatch'] or tuple(rule['target']) in safe):
                equivalent=any(r['source']==rule['source'] and r['target']==rule['target']
                               and r['objectives'] for r in rules)
                if not equivalent:raise ValueError('Uncovered ROM control: '+rule['id'])
                reason='equivalent-single-control'
            else:reason='non-playable-control'
        else:reason=rule['classification']
        dispositions[reason]+=1
    return dict(decoded_rules=len(rules),retained_rules=len(rules),
                decoded_input_windows=sum(r['timing'] is not None for r in rules),
                missing_decoded_rules=0,missing_ranked_choices=0,
                ranked_rules=sum(bool(r['objectives']) for r in rules),
                runtime_rules=len(native),dispositions=dict(sorted(dispositions.items())))


def write_move_table(path,data):
    """One structured rule per line keeps the full audit compact and diffable."""
    fields=[]
    for name,value in data.items():
        if isinstance(value,list):
            body=',\n'.join('    '+json.dumps(row,separators=(',',':')) for row in value)
            encoded='[\n'+body+'\n  ]'
        else:encoded=json.dumps(value,separators=(',',':'))
        fields.append('  '+json.dumps(name)+': '+encoded)
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as stream:
        stream.write('{\n'+',\n'.join(fields)+'\n}\n')
        temporary=Path(stream.name)
    temporary.replace(path)


def bundle(results,destination,include):
    destination.mkdir(parents=True,exist_ok=True);files={};profiles=[]
    rows={g:{o:{} for o in ('shortest','highest-score')} for g in ('dle21','ace')}
    candidates={g:[] for g in rows}
    policies={}; complete_rules={}
    report=json.loads((results/'report.json').read_text())
    if (not report['all_passed'] or report['completed']!=report['planned'] or
            report['failed_runs'] or report['verified_runs']!=len(report['results'])):
        raise ValueError('Full skill/difficulty verification is incomplete')
    for game in rows:
        rules=results/'rules'/game
        export_rom_moves.verify(rules)
        complete_rules[game]=json.loads((rules/'rules.json').read_text())
        policies[game]={o:json.loads((rules/(o+'-policy.json')).read_text()) for o in rows[game]}
    generation=destination/'generation-verification.json'
    shutil.copyfile(results/'report.json',generation)
    files[generation.name]=hashlib.sha256(generation.read_bytes()).hexdigest()
    for entry in report['results']:
        game=entry['game'];objective=entry['objective'];difficulty=entry['difficulty']
        if game not in rows or objective not in rows[game] or difficulty not in range(4):
            raise ValueError('Unsupported matrix profile')
        folder=(results/entry['directory']).resolve()
        if not folder.is_relative_to(results.resolve()):raise ValueError('Route outside results directory')
        data=json.loads((folder/'route.json').read_text())
        if (not entry['verified'] or not data['complete'] or not data['no_life_loss'] or
                not data['replay']['verified'] or data['configuration']['difficulty']!=difficulty):
            raise ValueError('Unverified route or difficulty mismatch')
        native=[json.loads(l) for l in (folder/'play.jsonl').read_text().splitlines() if l.startswith('{')]
        native=[r for r in native if r['type']=='rom_move']
        if len(native)!=len(data['moves']):raise ValueError('ROM identity/move alignment mismatch')
        for i,(live,move) in enumerate(zip(native,data['moves'])):
            if live['control']!=move['control'] or live['frame']!=move['frame']:raise ValueError('ROM/replay mismatch')
            state=live['scene']|(live['step']<<7)|(move['branch_state']<<14)
            row=(state,move['frame'],move['timing'],move['outcome'],move['control'])
            remaining=(data['move_count']-i,data['final_score']-move['score_before'])
            candidates[game].append((row,remaining))
        relative=Path(game)/('%s-d%d-%02d'%(entry['skill'],difficulty,entry['start']))/objective
        profile=dict(game=game,skill=entry['skill'],difficulty=difficulty,start=entry['start'],
                     start_delay=entry['start_delay'],directory=str(relative),
                     objective=objective,score=data['final_score'],moves=data['move_count'],verified=True)
        for name in ('route.json','route.trace'):
            target=destination/relative/name;target.parent.mkdir(parents=True,exist_ok=True)
            if (folder/name).resolve()!=target.resolve():shutil.copyfile(folder/name,target)
            files[str(relative/name)]=hashlib.sha256(target.read_bytes()).hexdigest()
        profiles.append(profile)
    coverage={};calibration_coverage={}
    for game in rows:
        states={r[0] for r,_ in candidates[game]}
        calibration_coverage[game]=dict(known_states=len(states),objectives={})
        for objective in rows[game]:
            rows[game][objective]=ranked_rows(candidates[game],policies[game][objective])
            action_states={r[0] for r in rows[game][objective]}
            calibration_coverage[game]['objectives'][objective]=dict(action_states=len(action_states),
                                                       waiting_states=sorted(states-action_states))
    lines=['// SPDX-License-Identifier: GPL-3.0-or-later',
           '// Complete ROM policies; sampled plays supply timing calibration only.',
           '// Reproduce with tools/offline-moves/verify_rom_matrix.py and bundle_rom_moves.py.']
    counts={};shared_counts={}
    for game,objectives in rows.items():
        counts[game]={}
        shared=sorted(set().union(*(set(items) for items in objectives.values())))
        if len(shared)>65536:raise ValueError('Move pool exceeds 16-bit index capacity')
        shared_counts[game]=len(shared)
        indices={row:i for i,row in enumerate(shared)}
        lines.append('static const ArcadeRomMove %s_moves[] = {'%game)
        lines += ['    {%dU, %dU, %d, %d, %d},'%r for r in shared]
        lines.append('};')
        data=dict(rules=complete_rules[game],moves=[dict(state=r[0],frame=r[1],timing=r[2],outcome=r[3],control=r[4]) for r in shared],policies={})
        for objective,items in objectives.items():
            suffix='fewest' if objective=='shortest' else 'max'
            ordered=sorted(items,key=lambda r:(r[0],items[r],r[4],r[1],r[2],r[3]))
            counts[game][objective]=len(ordered)
            order=[indices[r] for r in ordered]
            lines.append('static const uint16_t %s_moves_%s[] = {'%(game,suffix))
            lines += ['    '+', '.join(str(i) for i in order[start:start+12])+',' for start in range(0,len(order),12)]
            lines.append('};')
            data['policies'][objective]=order
        # Every decoded rule remains in the audit file. Native tables retain
        # every ranked alternative, including deliberate waits, not just rank 0
        # or scene/step contexts encountered by the replay matrix.
        rules=complete_rules[game]
        native,rule_orders=runtime_policy(rules)
        lines.append('static const ArcadeRomRule %s_rules[] = {'%game)
        lines += ['    {%d, %d, %d, %d},'%r for r in native]
        lines.append('};')
        data['rule_policies']={}
        for objective in objectives:
            suffix='fewest' if objective=='shortest' else 'max'
            order=rule_orders[objective]
            data['rule_policies'][objective]=order
            lines.append('static const uint16_t %s_rules_%s[] = {'%(game,suffix))
            lines += ['    '+', '.join(map(str,order[start:start+12]))+',' for start in range(0,len(order),12)]
            lines.append('};')
        data['native_rules']=[dict(state=r[0],window=r[1],outcome=r[2],control=r[3]) for r in native]
        inventory=destination/(game+'-inventory.json')
        shutil.copyfile(results/'rules'/game/'inventory.json',inventory)
        files[inventory.name]=hashlib.sha256(inventory.read_bytes()).hexdigest()
        coverage[game]=rule_coverage(json.loads(inventory.read_text()),rules,native,rule_orders)
        table=destination/(game+'-moves.json')
        write_move_table(table,data)
        files[table.name]=hashlib.sha256(table.read_bytes()).hexdigest()
    include.write_text('\n'.join(lines)+'\n')
    manifest=dict(schema=4,method='Complete decoded ROM rules and ranked runtime policies, with sampled replay timing calibrations',profiles=profiles,counts=counts,shared_counts=shared_counts,rom_coverage=coverage,calibration_coverage=calibration_coverage,
                  bundler_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  files=files,apk_include_sha256=hashlib.sha256(include.read_bytes()).hexdigest(),
                  all_scenes_proven=False,global_optimum_proven=False,
                  limits='Every decoded rule is retained. Runtime tables include all ranked alternatives; unranked and non-playable rules have explicit classifications in the audit. Replay timing validation remains separate from structural coverage.')
    move_tools.atomic_json(destination/'manifest.json',manifest)
    print('Bundled',len(profiles),'full-game routes:',counts,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--results',type=Path,required=True)
    p.add_argument('--destination',type=Path,default=score_routes.REPO/'android/moves/rom-tables')
    p.add_argument('--include',type=Path,default=score_routes.REPO/'android/app/jni/arcade_moves.inc')
    a=p.parse_args();bundle(a.results,a.destination,a.include)
