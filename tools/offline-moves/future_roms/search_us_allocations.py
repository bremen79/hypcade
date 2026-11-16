#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Try equally optimal allocations compatible with observed ROM exits.

Do not insist on a single arbitrary optimal room permutation. Keep the actual
prefix fixed, constrain a physically observed alternative exit, and recompute
the remaining resource allocation. This is bounded witness construction, not
a runtime policy or a probability estimator. Failed searches are inconclusive.
"""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import subprocess
import time

import cine_room_optimality
import dl1_allocation
from future_roms import dl1_continuation_costs
import rom_moves
import rom_proof
import rom_tables
import verify_cine_end
import verify_dl1_scheduler

ROOT = CORE


def itinerary(plan,final,costs,objective='highest-score'):
    visits=[];used=0
    for lap in range(3):
        for g in range(1,14):
            if g==13:
                scene=final[lap]+40;mask=(4,6,7)[lap]
            else:
                row=plan['groups'][g-1]
                scene=row['roots'][lap]
                mask=row['mask_after_'+('first','second','third')[lap]]
            if 80<=scene<=84:used|=1<<(scene-80)
            visits.append(dict(lap=lap,group=g,scene=scene,mask=mask,used=used,moves=costs[scene][0 if objective=='shortest' else 1]))
    return visits


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',type=Path,required=True)
    p.add_argument('--case',type=Path,required=True)
    p.add_argument('--selectors',type=Path,required=True)
    p.add_argument('--policy',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=600)
    p.add_argument('--attempts',type=int,default=48)
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);started=time.monotonic()
    original=json.loads((a.case/'allocation.json').read_text())['cases'][0]
    game=original['game'];row=original['results'][0]
    start_delay=json.loads((a.case/'witness/report.json').read_text()).get('start_delay',0)
    rom=rom_tables.load(a.rom,game)
    m=cine_room_optimality.Model(rom,game);g=m.graph();v=rom_proof.solve(g)
    objective=row['objective']
    costs=dl1_allocation.costs(m,g,v,objective)
    desc=verify_dl1_scheduler.descriptors(rom,game)
    groups=[desc[i]['scenes'] for i in range(1,13)]
    saved=next(c for c in json.loads(a.selectors.read_text())['cases'] if c['game']==game)
    if hashlib.sha256(rom).hexdigest()!=saved['rom_sha256']:raise ValueError('Wrong selector ROM')
    normal_groups=(0,0,4,8)[row['difficulty']]
    raw=normal_groups==0
    tables={(t['raw_hard'],t['hard']):{(r['used'],r['mask']):
        [(tuple(v),seed) for v,seed in r['support']] for r in t['rows']} for t in saved['selector_tables']}
    table=tables[raw,True]
    first_tables=[tables[raw,g>=normal_groups] for g in range(12)]
    binary=(a.case/'witness/build/us-witness').resolve()
    plan=row['allocation'];final=row['final_group'];target_score=row['score'];target_inputs=row['inputs']
    initial=itinerary(plan,final,costs,objective)[0]
    known={(0,0):initial};attempts=[];attained=False;chosen_pair=None
    visited_plans=set()
    for number in range(a.attempts):
        remaining=a.seconds-(time.monotonic()-started)
        if remaining<1:break
        folder=a.output/('attempt-%03d'%number);folder.mkdir(exist_ok=True)
        visits=itinerary(plan,final,costs,objective)
        visited_plans.add(tuple((r['scene'],r['mask']) for r in visits))
        path=folder/'plan.txt';path.write_text(''.join('%d %d %d %d\n'%(r['group'],r['scene'],r['moves'],r['mask']) for r in visits))
        trace=folder/'route.trace'
        with (folder/'play.jsonl').open('w') as out,(folder/'play.log').open('w') as err:
            try:
                result=subprocess.run([str(binary),str(a.rom.resolve()),game,'ace',str(start_delay),str(a.policy.resolve()),
                    str(trace.resolve()),'3600',str(row['difficulty'])],stdout=out,stderr=err,
                    env=dict(os.environ,HYPCADE_US_PLAN=str(path.resolve())),timeout=min(120,remaining))
                code=result.returncode
            except subprocess.TimeoutExpired:code=124
        records=rom_moves.records(folder/'play.jsonl')
        play=next((r for r in records if r['type']=='rom_play'),{})
        log=(folder/'play.log').read_text()
        failure=re.search(r'US timing frontier failed visit=(\d+).*observed=([0-9a-f]+):([0-9a-f]+)',log)
        rec=dict(attempt=number,returncode=code,play=play)
        primary=play.get('moves')==target_inputs if objective=='shortest' else play.get('score')==target_score
        if code==0 and primary and play.get('no_life_loss'):
            replayer=verify_cine_end.build(a.output/'replay-build');pc,frames=verify_cine_end.metadata(rom,game)
            with (folder/'replay.jsonl').open('w') as out,(folder/'replay.log').open('w') as err:
                check=subprocess.run([str(replayer),str(a.rom.resolve()),game,'ace',str(start_delay),'3600',
                    '--difficulty',str(row['difficulty']),'--replay',str(trace.resolve())],stdout=out,stderr=err,
                    env=dict(os.environ,HYPCADE_END_PC=str(pc),HYPCADE_END_FRAME0=str(frames[0]),
                             HYPCADE_END_FRAME1=str(frames[1])),timeout=120)
            replay_rows=rom_moves.records(folder/'replay.jsonl')
            rec['replay']=next((r for r in replay_rows if r['type']=='replay'),{})
            rec['rom_end']=next((r for r in replay_rows if r['type']=='rom_end'),{})
            replay_primary=(rec['replay'].get('move_count')==target_inputs if objective=='shortest' else rec['replay'].get('score')==target_score)
            attained=bool(check.returncode==0 and rec['replay'].get('verified') and rec['rom_end'].get('verified') and replay_primary)
            chosen_pair=[play.get('moves'),play.get('score')]
        if failure:
            visit=int(failure[1]);bits=(int(failure[2],16)<<64)|int(failure[3],16)
            seen=[i for i in range(128) if bits&(1<<i)]
            rec.update(failed_visit=visit,seen=seen)
        attempts.append(rec)
        report=dict(game=game,difficulty=row['difficulty'],objective=objective,start_delay=start_delay,target_score=target_score,target_inputs=target_inputs,
            attained=attained,actual=chosen_pair,attempts=attempts,
            seconds=time.monotonic()-started,
            peak_rss_kib=max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss),
            binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
            sources={n:hashlib.sha256((source_path(n)).read_bytes()).hexdigest() for n in
                ('search_us_allocations.py','dl1_continuation_costs.py','dl1_allocation.py','us_timing_witness.py')},scope=__doc__)
        (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(game,'allocation',number,'failed visit',rec.get('failed_visit'),'seen',rec.get('seen'),
              'score',play.get('score'),'attained',attained,flush=True)
        if attained or not failure:break
        if visit+1>=39:break
        # Fix the actual prefix that passed the original witness guards.
        for r in visits[:visit+1]:known[r['lap'],r['group']-1]=r
        nxt=visits[visit+1];group=nxt['group']
        if group==13:break
        prior_mask=next((r['mask'] for r in reversed(visits[:visit+1]) if r['group']==group),0)
        used=visits[visit]['used']
        replacement=None
        next_table=first_tables[group-1] if nxt['lap']==0 else table
        for (choice,mask,used_after),phase in next_table[used,prior_mask]:
            root=(groups[group-1][choice]+(0 if nxt['lap']==0 and group<=normal_groups else 40)
                  if choice<3 else 80+choice-3)
            if root not in seen or root==nxt['scene']:continue
            trial=dict(known)
            trial[nxt['lap'],group-1]=dict(scene=root,mask=mask,used=used_after)
            if raw:
                candidate=dl1_continuation_costs.allocate(groups,table,costs,trial)
            else:
                ordinary={key:value for key,value in trial.items() if key[1]<12}
                candidate=dl1_allocation.allocate_three(groups,first_tables,table,costs,normal_groups,known=ordinary)
            total=dl1_allocation.add(candidate['value'],*(costs[s+40] for s in final))
            if (total[0]==target_inputs if objective=='shortest' else -total[0]==target_score):
                replacement=candidate;known=trial
                rec['new_exit']=root
                break
        if replacement is None:
            # A failed exit may be fixed by a different equally optimal
            # incoming room, rather than changing the next room alone.
            # Keep the earlier physically attained prefix; never alter ROM
            # state or accept a worse primary bound to manufacture success.
            for back in range(visit,0,-1):
                incoming=visits[back];group=incoming['group']
                if group==13:continue
                prefix=visits[:back]
                prior_mask=next((r['mask'] for r in reversed(prefix) if r['group']==group),0)
                used=prefix[-1]['used']
                next_table=first_tables[group-1] if incoming['lap']==0 else table
                for (choice,mask,used_after),phase in next_table[used,prior_mask]:
                    root=(groups[group-1][choice]+(0 if incoming['lap']==0 and group<=normal_groups else 40)
                          if choice<3 else 80+choice-3)
                    if root==incoming['scene']:continue
                    trial={(r['lap'],r['group']-1):r for r in prefix if r['group']<13}
                    trial[incoming['lap'],group-1]=dict(scene=root,mask=mask,used=used_after)
                    try:
                        if raw:
                            candidate=dl1_continuation_costs.allocate(groups,table,costs,trial)
                        else:
                            candidate=dl1_allocation.allocate_three(groups,first_tables,table,costs,normal_groups,known=trial)
                    except ValueError as error:
                        if 'No selector-support allocation' not in str(error):raise
                        continue
                    total=dl1_allocation.add(candidate['value'],*(costs[s+40] for s in final))
                    primary=(total[0]==target_inputs if objective=='shortest' else -total[0]==target_score)
                    signature=tuple((r['scene'],r['mask']) for r in itinerary(candidate,final,costs,objective))
                    if primary and signature not in visited_plans:
                        replacement=candidate;known=trial
                        rec['backtrack']=dict(visit=back,previous_root=incoming['scene'],replacement_root=root)
                        break
                if replacement is not None:break
        if replacement is None:break
        plan=replacement
        (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
