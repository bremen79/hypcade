#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""One-life whole-game bounds and original-ROM attainment verification.

Scene/exit Bellman certificates are checked separately by verify_cost_runtime.
US refresh transitions form a relaxation: an independently replayed winning
trajectory must attain its primary bound. No probability law is assumed.
Euro/Italian policies maximize/minimize every already selected room queue.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import dl1_allocation
import dle_scheduler_graph
import rom_moves
import rom_tables
import verify_cine_end
import verify_cost_runtime

ROOT=Path(__file__).resolve().parent
INPUTS=ROOT/'proof-inputs'
FIELDS=('fewest','score_at_fewest','highest_score','fewest_at_score')


def initial_bounds(bundle):
    """Compose independent scene potentials through ROM scheduler support."""
    bundle=Path(bundle);rows=[]
    support=json.loads((INPUTS/'us-selectors.json').read_text())
    for case in support['cases']:
        game=case['game'];table=json.loads((bundle/(game+'.json')).read_text())
        proof=table['certificate'];graph=proof['graph'];values=proof['values']
        model=SimpleNamespace(spec=proof['inventory']['layout'])
        groups=[case['descriptors'][str(i)]['scenes'] for i in range(1,13)]
        tables={(t['raw_hard'],t['hard']):{(r['used'],r['mask']):
            [(tuple(v),seed) for v,seed in r['support']] for r in t['rows']}
            for t in case['selector_tables']}
        late=game in ('lair_e','lair_f');offset=42 if late else 40
        for objective in ('shortest','highest-score'):
            costs=dl1_allocation.costs(model,graph,values,objective)
            for difficulty,normal in enumerate((0,0,4,8)):
                raw=normal==0;first=[tables[raw,g>=normal] for g in range(12)]
                later=tables[raw,True]
                plan=dl1_allocation.allocate_three(groups,first,later,costs,normal,
                    offset=offset,boundaries=(0,) if late else range(32))
                dl1_allocation.verify_three(plan,first,later,costs,groups,normal,offset)
                final=case['descriptors']['13']['scenes'][::-1]
                total=dl1_allocation.add(plan['value'],*(costs[s+offset] for s in final))
                moves,score=(total[0],-total[1]) if objective=='shortest' else (total[1],-total[0])
                rows.append(dict(game=game,skill='ace',difficulty=difficulty,objective=objective,
                    moves=moves,score=score,primary_bound=moves if objective=='shortest' else score))
    dle=json.loads((INPUTS/'dle-scheduler.json').read_text());dle_scheduler_graph.verify(dle)
    for objective in ('shortest','highest-score'):
        m,s=('fewest','score_at_fewest') if objective=='shortest' else ('fewest_at_score','highest_score')
        rows.append(dict(game='dle21',skill='ace',difficulty=0,objective=objective,
            moves=dle['initial'][m],score=dle['initial'][s],
            primary_bound=dle['initial'][m if objective=='shortest' else s]))
    for game in ('ace','sae'):
        for skill in ('cadet','captain','ace'):
            for difficulty in (range(4) if game=='ace' else range(2)):
                name='ace-'+skill+'-proof.json' if game=='ace' else 'sae-%s-d%d-proof.json'%(skill,difficulty)
                proof=json.loads((bundle/'proofs'/name).read_text())
                variants=[proof['values']] if game=='ace' else proof['values']
                for objective in ('shortest','highest-score'):
                    m,s=('fewest','score_at_fewest') if objective=='shortest' else ('fewest_at_score','highest_score')
                    pair=min((v[m][0],-v[s][0]) if objective=='shortest' else
                             (-v[s][0],v[m][0]) for v in variants)
                    moves,score=(pair[0],-pair[1]) if objective=='shortest' else (pair[1],-pair[0])
                    rows.append(dict(game=game,skill=skill,difficulty=difficulty,objective=objective,
                        moves=moves,score=score,primary_bound=moves if objective=='shortest' else score))
    if len(rows)!=86:raise ValueError('Incomplete Cinematronics initial-bound matrix')
    return rows


def replay_classic(roms,bounds,output):
    """Fixed physical witnesses certify support endpoints, not runtime coverage."""
    output.mkdir(parents=True,exist_ok=True)
    binary=verify_cine_end.build(output/'build')
    plays=json.loads((INPUTS/'attaining-plays.json').read_text())['cases']
    expected={(r['game'],r['difficulty'],r['objective']):r for r in bounds}
    if len(plays)!=50:raise ValueError('Expected all 50 classic-board objective witnesses')
    results=[]
    for case in plays:
        key=case['game'],case['difficulty'],case['objective'];target=expected[key]
        payload=case['trace'].encode('utf-8')
        if hashlib.sha256(payload).hexdigest()!=case['sha256']:
            raise ValueError('Attainment schedule changed')
        header=case['trace'].splitlines()[0].split()
        metric=int(header[-1] if case['objective']=='shortest' else header[-2])
        if metric!=target['primary_bound']:raise ValueError('Schedule cannot attain current bound')
        folder=output/('%s-d%d-%s'%key);folder.mkdir(exist_ok=True)
        trace=folder/'route.trace';trace.write_bytes(payload)
        path=roms/(case['game']+'.zip');rom=rom_tables.load(path,case['game'])
        pc,frames=verify_cine_end.metadata(rom,case['game'])
        env=dict(os.environ,HYPCADE_END_PC=str(pc),HYPCADE_END_FRAME0=str(frames[0]),HYPCADE_END_FRAME1=str(frames[1]))
        with (folder/'replay.jsonl').open('w') as log,(folder/'replay.log').open('w') as err:
            run=subprocess.run([str(binary),str(path.resolve()),case['game'],'ace',str(case['start_delay']),
                '3600','--difficulty',str(case['difficulty']),'--replay',str(trace.resolve())],
                stdout=log,stderr=err,env=env,timeout=120)
        records=rom_moves.records(folder/'replay.jsonl')
        replay=next((r for r in records if r['type']=='replay'),{})
        end=next((r for r in records if r['type']=='rom_end'),{})
        primary=replay.get('move_count' if case['objective']=='shortest' else 'score')
        ok=run.returncode==0 and replay.get('verified') and end.get('verified') and primary==target['primary_bound']
        row=dict(**target,verified=bool(ok),replay=replay,rom_end=end);results.append(row)
        (output/'report.json').write_text(json.dumps(dict(cases=results),indent=2)+'\n')
        print(*key,'attained',ok,flush=True)
        if not ok:raise ValueError('Original-ROM attainment replay failed: '+str(key))
    return results


def check_space_watch(path,bounds,bundle):
    """Require a current, independently replayed attaining play in all 36 cases."""
    report=json.loads(path.read_text())
    if report['include_sha256']!=hashlib.sha256((bundle/'arcade_moves.inc').read_bytes()).hexdigest():
        raise ValueError('Watch attainment used a different production policy')
    for name,digest in report['source_sha256'].items():
        if hashlib.sha256((ROOT.parents[1]/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Watch attainment source changed: '+name)
    certified=[]
    for target in (r for r in bounds if r['game'] in ('ace','sae')):
        matches=[]
        for row in report['results']:
            proof=row['result'];replay=row.get('independent_replay') or {}
            same=(row['game']==target['game'] and row['skill']==target['skill'] and
                  row['difficulty']==target['difficulty'] and
                  row['mode']==(2 if target['objective']=='shortest' else 1))
            metric='accepted_commands' if target['objective']=='shortest' else 'score'
            if (same and row['verified'] and not proof.get('losses',1) and proof.get('rom_end') and
                    replay.get('verified') and proof.get(metric)==target['primary_bound'] and
                    replay.get(metric)==target['primary_bound']):
                matches.append(row)
        if not matches:raise ValueError('No independently replayed Watch attainment: '+str(target))
        certified.append(dict(**target,watch=matches[0]))
    if len(certified)!=36:raise ValueError('Incomplete Space Ace objective matrix')
    return certified


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,default=ROOT.parents[1]/'android/moves/strategies')
    parser.add_argument('--roms',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--replay-classic',action='store_true')
    parser.add_argument('--watch-report',type=Path,help='Check Space Ace attainment from original-CPU Watch and independent physical replays')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    verify_cost_runtime.verify_bundle(args.bundle,roms=args.roms)
    bounds=initial_bounds(args.bundle)
    (args.output/'bounds.json').write_text(json.dumps(dict(cases=bounds,
        scope='One-life primary support bounds; physical attainment checked separately'),indent=2)+'\n')
    print('Recomputed',len(bounds),'Cine one-life objective bounds')
    if args.replay_classic:
        if not args.roms:parser.error('--replay-classic requires --roms')
        replay_classic(args.roms,bounds,args.output/'classic-replays')
    if args.watch_report:
        cases=check_space_watch(args.watch_report,bounds,args.bundle)
        (args.output/'space-ace-attainment.json').write_text(json.dumps(dict(cases=cases),indent=2)+'\n')
        print('All 36 Space Ace primary optima attained and independently replayed with the bundled selector')


if __name__=='__main__':main()
