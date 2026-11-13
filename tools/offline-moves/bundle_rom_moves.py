#!/usr/bin/env python3
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


def bundle(results,destination,include):
    destination.mkdir(parents=True,exist_ok=True);files={};profiles=[]
    rows={g:{o:{} for o in ('shortest','highest-score')} for g in ('dle21','ace')}
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
            rank=remaining if objective=='shortest' else (-remaining[1],remaining[0])
            old=rows[game][objective].get(row)
            rows[game][objective][row]=min(old,rank) if old else rank
        relative=Path(game)/('%s-d%d-%02d'%(entry['skill'],difficulty,entry['start']))/objective
        profile=dict(game=game,skill=entry['skill'],difficulty=difficulty,start=entry['start'],
                     start_delay=entry['start_delay'],directory=str(relative),
                     objective=objective,score=data['final_score'],moves=data['move_count'],verified=True)
        for name in ('route.json','route.trace'):
            target=destination/relative/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(folder/name,target)
            files[str(relative/name)]=hashlib.sha256(target.read_bytes()).hexdigest()
        profiles.append(profile)
    lines=['// SPDX-License-Identifier: GPL-3.0-or-later',
           '// ROM-state moves from complete death-free, independently replayed routes.',
           '// Reproduce with tools/offline-moves/verify_rom_matrix.py and bundle_rom_moves.py.']
    counts={}
    for game,objectives in rows.items():
        counts[game]={}
        for objective,items in objectives.items():
            suffix='fewest' if objective=='shortest' else 'max'
            ordered=sorted(items,key=lambda r:(r[0],items[r],r[4],r[1],r[2],r[3]))
            counts[game][objective]=len(ordered)
            lines.append('static const ArcadeRomMove %s_moves_%s[] = {'%(game,suffix))
            lines += ['    {%dU, %dU, %d, %d, %d},'%r for r in ordered]
            lines.append('};')
            table=destination/(game+'-'+objective+'.json')
            move_tools.atomic_json(table,[dict(state=r[0],frame=r[1],timing=r[2],outcome=r[3],control=r[4]) for r in ordered])
            files[table.name]=hashlib.sha256(table.read_bytes()).hexdigest()
    include.write_text('\n'.join(lines)+'\n')
    manifest=dict(schema=1,method='ROM scene/step identities with separately ranked move sets',profiles=profiles,counts=counts,
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
