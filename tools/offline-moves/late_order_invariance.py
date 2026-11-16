#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Factor the fixed-version E/F scheduler into independent eight-mask DAGs.

Every phase may choose any original supported transition. Prove that every
such choice has the same remaining lexicographic values, rather than assuming
that physical timing can realize freely chosen phases. Complete-game physical
attainment and retry composition remain separate obligations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

import cine_room_optimality
import dl1_selector
import rom_kernel
import rom_proof
import rom_tables
import verify_dl1_scheduler

ROOT=Path(__file__).resolve().parent
FIELDS=('fewest','score_at_fewest','highest_score','fewest_at_score')


def factor(transitions,costs):
    if len(costs)!=3:raise ValueError('Expected exactly three variant costs')
    values={7:(0,)*len(costs[0])};edges={7:[]}
    for mask in sorted(range(7),key=lambda m:m.bit_count(),reverse=True):
        options=[];edges[mask]=[]
        for (choice,following,used),_ in transitions[0,mask]:
            if used or choice not in range(3) or mask&(1<<choice) or following!=mask|(1<<choice):
                raise ValueError('Selector is not a fresh-variant permutation')
            options.append(tuple(a+b for a,b in zip(costs[choice],values[following])))
            edges[mask].append(dict(choice=choice,target=following))
        if not options or any(v!=options[0] for v in options):
            raise ValueError('Selector branches have unequal remaining values')
        values[mask]=options[0]
    return dict(values=values,edges=edges)


def certify(rom,game,build):
    if game not in ('lair_e','lair_f'):raise ValueError('Fixed-version certificate supports E/F only')
    model=cine_room_optimality.Model(rom,game);graph=model.graph();values=rom_proof.solve(graph)
    index={s:u for u,s in enumerate(graph['states'])}
    desc=verify_dl1_scheduler.descriptors(rom,game)
    if set(desc)!=set(range(1,14)) or any(d['flags']!=(10 if g==13 else 2) or d['mask']!=7 for g,d in desc.items()):
        raise ValueError('Unexpected late-board group structure')
    kernel=rom_kernel.Kernel(rom,build)
    table,audit=dl1_selector.extract(rom,game,kernel,True,True)
    factors=[];total=[0]*4
    def cost(scene):
        result=tuple(values[f][index[scene,0]] for f in FIELDS)
        if any(v is None for v in result):raise ValueError('Room lacks a surviving completion')
        return result
    for group in range(1,13):
        roots=[s+42 for s in desc[group]['scenes']]
        node=factor(table,[cost(s) for s in roots]);node.update(group=group,roots=roots)
        factors.append(node);total=[a+b for a,b in zip(total,node['values'][0])]
    final=[];final_cases=0
    for mask,choice in ((0,2),(4,1),(6,0)):
        root=desc[13]['scenes'][choice]+42
        ram=dl1_selector.memory(rom,game,13,mask,0,True,True)
        for seed in range(128):
            out,_=kernel.call(ram,dl1_selector.entry_pc(rom),refresh=seed)
            if dl1_selector.decode(rom,game,13,mask,0,out,True,True)!=(choice,mask|(1<<choice),0):
                raise ValueError('Final group is not fixed descending exhaustion')
            final_cases+=1
        final.append(root);total=[a+b for a,b in zip(total,cost(root))]
    playable={s for node in factors for s in node['roots']}|set(final)
    _,mixed=verify_dl1_scheduler.room_effects(model,graph,playable)
    if mixed:raise ValueError('Room action changes scheduler effect')
    return dict(game=game,rom_sha256=hashlib.sha256(rom).hexdigest(),operator_levels=[0,1],
        factors=factors,factor_states=8*12,final_group=final,potential=dict(zip(FIELDS,total)),
        selector_audit=audit,final_selector_cases=final_cases,
        conclusion='Every supported phase yields the same remaining value at each mask; no phase distribution or attainability assumption is needed for these macro values',
        whole_game_optimality_proven=False,
        remaining='Bind actual game progression, accepted-input feasibility and life-restart contexts before claiming complete game or recovery optimality')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--roms',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);start=time.monotonic();cases=[]
    for game in ('lair_e','lair_f'):
        cases.append(certify(rom_tables.load(a.roms/(game+'.zip'),game),game,a.output/'build'))
        print(game,cases[-1]['potential'],flush=True)
    result=dict(cases=cases,seconds=time.monotonic()-start,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        sources={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
            ('late_order_invariance.py','verify_dl1_scheduler.py','cine_room_optimality.py','dl1_selector.py','rom_proof.py','rom_tables.py','rom_kernel.py','rom_kernel.c')})
    (a.output/'report.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
