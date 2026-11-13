#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Package sampled, verified runtime rows for the APK, not complete ROM rules.

Use export_rom_moves.py to export all decoded table windows.
This packager retains accepted timings from the runtime contexts actually seen.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import moves as move_tools
import score_routes
import export_rom_moves


def ranked_rows(candidates, policy):
    """Use all proven branches, retaining this objective's choice to act or wait.

    A route's objective is not a coverage boundary. Once a player takes another
    branch, either objective needs the verified continuation from that state.
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
    states={row[0] for row,_ in candidates}
    covered={row[0] for row in items}
    missing=sorted(s for s in states-covered if best[(s&127,(s>>7)&127)]['control'])
    if missing:
        contexts=[dict(scene=s&127,step=(s>>7)&127,branch=s>>14) for s in missing]
        raise ValueError('No verified continuation for ROM policy states: '+str(contexts))
    return items


def bundle(results,destination,include):
    destination.mkdir(parents=True,exist_ok=True);files={};profiles=[]
    rows={g:{o:{} for o in ('shortest','highest-score')} for g in ('dle21','ace')}
    candidates={g:[] for g in rows}
    policies={}
    for game in rows:
        rules=results/'rules'/game
        export_rom_moves.verify(rules)
        policies[game]={o:json.loads((rules/(o+'-policy.json')).read_text()) for o in rows[game]}
    report=json.loads((results/'report.json').read_text())
    if (not report['all_passed'] or report['completed']!=report['planned'] or
            report['failed_runs'] or report['verified_runs']!=len(report['results'])):
        raise ValueError('Full skill/difficulty verification is incomplete')
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
    coverage={}
    for game in rows:
        states={r[0] for r,_ in candidates[game]}
        coverage[game]=dict(known_states=len(states),objectives={})
        for objective in rows[game]:
            rows[game][objective]=ranked_rows(candidates[game],policies[game][objective])
            action_states={r[0] for r in rows[game][objective]}
            coverage[game]['objectives'][objective]=dict(action_states=len(action_states),
                                                       waiting_states=sorted(states-action_states))
    lines=['// SPDX-License-Identifier: GPL-3.0-or-later',
           '// ROM-state moves from complete death-free, independently replayed routes.',
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
        data=dict(moves=[dict(state=r[0],frame=r[1],timing=r[2],outcome=r[3],control=r[4]) for r in shared],policies={})
        for objective,items in objectives.items():
            suffix='fewest' if objective=='shortest' else 'max'
            ordered=sorted(items,key=lambda r:(r[0],items[r],r[4],r[1],r[2],r[3]))
            counts[game][objective]=len(ordered)
            order=[indices[r] for r in ordered]
            lines.append('static const uint16_t %s_moves_%s[] = {'%(game,suffix))
            lines += ['    '+', '.join(str(i) for i in order[start:start+12])+',' for start in range(0,len(order),12)]
            lines.append('};')
            data['policies'][objective]=order
        table=destination/(game+'-moves.json')
        move_tools.atomic_json(table,data)
        files[table.name]=hashlib.sha256(table.read_bytes()).hexdigest()
    include.write_text('\n'.join(lines)+'\n')
    manifest=dict(schema=3,method='One shared move file per game with 16-bit policy indices; both objectives cover the union of verified branches, filtered by their ROM action/wait policy',profiles=profiles,counts=counts,shared_counts=shared_counts,branch_coverage=coverage,
                  bundler_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  files=files,apk_include_sha256=hashlib.sha256(include.read_bytes()).hexdigest(),
                  all_scenes_proven=False,global_optimum_proven=False,
                  limits='Verified natural full games cover sampled starts, all skills and all operator difficulties. Merged lookup and Watch Mode require separate verification; retry and all-context coverage are not claimed.')
    move_tools.atomic_json(destination/'manifest.json',manifest)
    print('Bundled',len(profiles),'full-game routes:',counts,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--results',type=Path,required=True)
    p.add_argument('--destination',type=Path,default=score_routes.REPO/'android/moves/rom-tables')
    p.add_argument('--include',type=Path,default=score_routes.REPO/'android/app/jni/arcade_moves.inc')
    a=p.parse_args();bundle(a.results,a.destination,a.include)
