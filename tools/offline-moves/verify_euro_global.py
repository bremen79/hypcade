#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate exported Euro/Italian global room policies against live ROM queues.

Original CPU/driver/player, shared packaged selector, physical-input replay.
Queue permutations are summed, not searched. Android is not started.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

import euro_moves
import euro_optimality
import euro_tables
import rom_proof


def run(args):
    args.output.mkdir(parents=True,exist_ok=True);started=time.monotonic()
    binary=euro_moves.build(args.output/'build').resolve()
    comparison=json.loads((args.policies/'report.json').read_text())
    results=[]
    for game in ('laireuro','lair_ita'):
        rom=euro_tables.load(args.roms/(game+'.zip'),game)
        model=euro_optimality.Model(rom,game);model.verify_room_boundaries();graph=model.graph();values=rom_proof.solve(graph)
        index={s:i for i,s in enumerate(graph['states'])}
        game_case=next(r for r in comparison['cases'] if r['game']==game)
        if game_case['rom_sha256']!=hashlib.sha256(rom).hexdigest():raise ValueError('Policy ROM fingerprint differs')
        program=args.output/(game+'.bin');program.write_bytes(rom)
        for level in range(4):
            banks=list(euro_tables.LAYOUTS[game]['banks']);banks[0]=(banks[0]&63)|((3-level)<<6)
            for objective in ('shortest','highest-score'):
                policy=args.policies/game/(objective+'.policy')
                if hashlib.sha256(policy.read_bytes()).hexdigest()!=game_case['artifacts'][policy.name]:raise ValueError('Exported policy changed')
                for miss in (0,20):
                    tag='%s-d%d-%s-miss%d'%(game,level,objective,miss);folder=args.output/tag;folder.mkdir(exist_ok=True)
                    trace=folder/'physical.trace';proofs=[];queue=None
                    command=[str(binary),str(program.resolve()),str(policy.resolve()),str(trace.resolve()),'0','0',str(miss)]
                    for replay in (0,1):
                        finished=subprocess.run(command+[str(replay),*(str(b) for b in banks),
                            str(int(euro_tables.LAYOUTS[game]['per_player_difficulty']))],capture_output=True,text=True,timeout=120)
                        (folder/('replay.log' if replay else 'play.log')).write_text(finished.stderr)
                        (folder/('replay.json' if replay else 'play.json')).write_text(finished.stdout)
                        proof=json.loads(finished.stdout);proof['returncode']=finished.returncode;proofs.append(proof)
                        match=re.search(r'^QUEUE count=(\d+) (.*)$',finished.stderr,re.M)
                        if not replay and match:
                            queue=[int(v) for v in match[2].split()]
                            if len(queue)!=int(match[1]):raise ValueError('Incomplete ROM queue publication')
                    verified=all(p['returncode']==0 and p.get('win') for p in proofs)
                    verified &= all(proofs[0].get(k)==proofs[1].get(k) for k in ('score','moves','lives','initial_lives','ms','difficulty'))
                    expected=None;matches=None
                    if not miss:
                        if queue is None:raise ValueError('Missing actual ROM queue')
                        active=queue[:12] if game=='lair_ita' else queue
                        roots=[model.data['roots'][0],*active,model.data['roots'][1]]
                        totals={k:sum(v[index[r]] for r in roots) for k,v in values.items()}
                        expected=[totals['fewest'],totals['score_at_fewest']] if objective=='shortest' else [totals['fewest_at_score'],totals['highest_score']]
                        matches=[proofs[0].get('moves'),proofs[0].get('score')]==expected
                        verified &= matches
                    row=dict(game=game,difficulty=level,objective=objective,miss=miss,verified=bool(verified),
                             actual_queue=queue,expected=expected,matches_both_bounds=matches,proofs=proofs,
                             recovery_scope='One omitted-input death and physical replay; arbitrary retries covered separately by queue/room invariants' if miss else None)
                    results.append(row)
                    report=dict(results=results,sources=euro_moves.identity(),
                        verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        seconds=time.monotonic()-started,all_completed_cases_passed=all(r['verified'] for r in results),
                        scope='Host production European CPU/driver, packaged selector, 8ms polling/17ms queue, no Android runtime')
                    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
                    print(tag,'PASS' if verified else 'FAIL','moves',proofs[0].get('moves'),'score',proofs[0].get('score'),'expected',expected,flush=True)
                    if not verified:raise ValueError('Exported European strategy failed its ROM-queue bound or replay')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--roms',type=Path,required=True);p.add_argument('--policies',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);run(p.parse_args())


if __name__=='__main__':main()
