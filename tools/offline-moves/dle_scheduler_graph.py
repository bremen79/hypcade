#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compose DLE21's authored scheduler with complete per-exit room potentials.

Histories retain only consumed variant bits, never room permutations. Nature
branches must have identical values; otherwise refresh-phase modeling remains
necessary and certification fails. Accidental-retry queue composition is not
claimed by this initial-game scheduler certificate.
"""
import argparse
from collections import defaultdict,deque
import hashlib
import json
from pathlib import Path
import resource
import time

import cine_room_optimality
import rom_controls
import dle_retry_rules
import rom_proof
import rom_tables
import verify_dl1_scheduler

FIELDS=('fewest','score_at_fewest','highest_score','fewest_at_score')


def verify(certificate):
    """Check the expanded macro Bellman equalities without running its solver."""
    count=len(certificate['states']);pot=certificate['potential']
    if set(pot)!=set(FIELDS) or any(len(a)!=count for a in pot.values()):
        raise ValueError('Invalid macro potential dimensions')
    dependencies=[]
    for u,variants in enumerate(certificate['branches']):
        deps=set()
        for branch in variants:
            shortest=[];highest=[];tails=set()
            for edge in branch['exits']:
                target=edge['target']
                if target is not None and not 0<=target<count:raise ValueError('Invalid macro target')
                if target is not None:deps.add(target)
                tail={k:0 if target is None else pot[k][target] for k in FIELDS}
                tails.add(tuple(tail[k] for k in FIELDS))
                total={k:edge['room_values'][k]+tail[k] for k in FIELDS}
                shortest.append((total['fewest'],-total['score_at_fewest']))
                highest.append((-total['highest_score'],total['fewest_at_score']))
            if len(tails)!=1:raise ValueError('Unequal room-exit continuation costs')
            m,negative_s=min(shortest);negative_max,tie_m=min(highest)
            actual=tuple(pot[k][u] for k in FIELDS)
            if actual!=(m,-negative_s,-negative_max,tie_m):
                raise ValueError('Macro Bellman equality differs for a Nature alternative')
        dependencies.append(deps)
    pending={u for u,d in enumerate(dependencies) if not d};done=set()
    while pending:
        done.update(pending)
        pending={u for u,d in enumerate(dependencies) if u not in done and d<=done}
    if len(done)!=count:raise ValueError('Cyclic macro certificate')
    if certificate['initial']!={k:certificate['initial_bridge'][k]+pot[k][0] for k in FIELDS}:
        raise ValueError('Initial bridge composition differs')


def compose(rom,native,cover_deaths=False):
    if native['rom_sha256']!=hashlib.sha256(rom).hexdigest():raise ValueError('DLE selector ROM differs')
    model=cine_room_optimality.Model(rom,'dle21')
    graph,values,removed=rom_controls.simplify_controls(model,model.graph())
    roots={s:i for i,s in enumerate(graph['states'])}
    desc=verify_dl1_scheduler.descriptors(rom,'dle21')
    playable={0}|{s for d in desc.values() for s in d['scenes']}
    effects,_=verify_dl1_scheduler.room_effects(model,graph,playable)
    all_effects=set().union(*(effects[roots[s,0]] for s in playable))
    conditional={}
    for effect in sorted(all_effects):
        restricted=dict(graph)
        restricted['goals']=[u for u in graph['goals'] if
            (effect==('win',) and graph['states'][u][0]!=128) or
            (graph['states'][u][0]==128 and list(model.return_labels)[graph['states'][u][1]]==effect)]
        conditional[effect]=rom_proof.solve(restricted)
    for raw in rom[0x22f4:rom.index(255,0x22f4)]:
        a=raw&127;b=a+1
        if any(values[k][roots[a,0]]!=values[k][roots[b,0]] for k in FIELDS):
            raise ValueError('DLE mirror changes a lexicographic room value')
    selector={(r['episode'],r['history']):r['targets'] for r in native['transitions']}
    fatal={}
    for scene,step in graph['states']:
        if scene==128:continue
        record=model.record(scene,step)
        if record['death']:fatal.setdefault(scene,set()).add(bool(record['trailer'][4]&4))
    initial=(1,(0,)*24);states=[initial];index={initial:0};branches=[]
    for episode,history in states:
        branch=[]
        for room,mask,step in selector[episode,history[episode]]:
            if step:raise ValueError('Fresh scheduler unexpectedly installs a retry step')
            following=list(history);following[episode]=mask;following=tuple(following)
            exits=[]
            for effect in sorted(effects[roots[room,0]]):
                room_values={k:conditional[effect][k][roots[room,0]] for k in FIELDS}
                if room_values['fewest'] is None:continue
                if effect==('win',):target=None
                else:
                    ep=episode+1 if effect==('next',) else effect[1]
                    if ep not in desc:raise ValueError('Scheduler exits authored descriptors')
                    state=ep,following
                    if state not in index:index[state]=len(states);states.append(state)
                    target=index[state]
                exits.append(dict(effect=effect,target=target,room_values=room_values))
            if not exits:raise ValueError('ROM-selected room has no surviving completion')
            row=dict(room=room,history_after=mask,exits=exits)
            if cover_deaths:
                recovery=[]
                for immediate in sorted(fatal.get(room,())):
                    if immediate:
                        recovery.append(dict(kind='immediate',target=None,pending_room=None))
                        continue
                    ep=episode+1
                    if ep not in desc:raise ValueError('Accidental failure exits authored descriptors')
                    state=ep,following
                    if state not in index:index[state]=len(states);states.append(state)
                    recovery.append(dict(kind='advance',target=index[state],
                        pending_room=None if (room|128) in dle_retry_rules.EXCLUDED else room))
                row['recoveries']=recovery
            branch.append(row)
        branches.append(branch)
    deps=[set(e['target'] for b in choices for e in b['exits'] if e['target'] is not None) for choices in branches]
    parents=defaultdict(set)
    for u,ds in enumerate(deps):
        for v in ds:parents[v].add(u)
    ready=deque(u for u,ds in enumerate(deps) if not ds);order=[]
    result={k:[None]*len(states) for k in FIELDS};ranked=[]
    for _ in states:ranked.append({})
    while ready:
        u=ready.popleft();order.append(u)
        nature={o:[] for o in ('shortest','highest-score')}
        for branch in branches[u]:
            choices={o:[] for o in nature}
            for edge in branch['exits']:
                target=edge['target'];tail={k:0 if target is None else result[k][target] for k in FIELDS}
                total={k:edge['room_values'][k]+tail[k] for k in FIELDS}
                choices['shortest'].append(((total['fewest'],-total['score_at_fewest']),edge['effect'],target))
                choices['highest-score'].append(((-total['highest_score'],total['fewest_at_score']),edge['effect'],target))
            for objective,options in choices.items():
                ordered=sorted(options,key=lambda x:(x[0],x[1]));nature[objective].append(ordered[0][0])
                ranked[u].setdefault(objective,[]).append(dict(room=branch['room'],choices=ordered))
        for objective,variants in nature.items():
            if len(set(variants))!=1:raise ValueError('DLE refresh alternatives have unequal values; timing cannot be eliminated')
        result['fewest'][u],neg=nature['shortest'][0];result['score_at_fewest'][u]=-neg
        neg,result['fewest_at_score'][u]=nature['highest-score'][0];result['highest_score'][u]=-neg
        for parent in parents[u]:
            deps[parent].remove(u)
            if not deps[parent]:ready.append(parent)
    if len(order)!=len(states):raise ValueError('DLE macro scheduler contains a surviving cycle')
    bridge={k:conditional[('explicit',1)][k][roots[0,0]] for k in FIELDS}
    initial_values={k:bridge[k]+result[k][0] for k in FIELDS}
    # The same suffix must apply to every successful exit of a room. This
    # is the translation-invariance proof for all its off-policy records,
    # not just for the selected optimal room-entry trajectory.
    exit_contexts=0
    for choices in branches:
        for branch in choices:
            tails={tuple(0 if e['target'] is None else result[k][e['target']] for k in FIELDS)
                   for e in branch['exits']}
            if len(tails)!=1:raise ValueError('DLE room exits do not share one continuation value')
            exit_contexts+=1
    return dict(states=states,branches=branches,ranked=ranked,potential=result,initial=initial_values,
                nature_branches_equal_at_every_state=True,initial_bridge=bridge,
                room_exit_continuation_equal_contexts=exit_contexts,
                policy_theorem='Adding the common suffix preserves both local lexicographic rankings at every surviving record inside these room contexts',
                death_coverage=cover_deaths,
                scope=('Surviving macro values with accidental-advance state closure; pending-room cost composition remains separate' if cover_deaths else
                       'Complete fresh-game authored scheduler and per-exit room bounds; no intentional deaths; retry queues separate'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',type=Path,required=True);p.add_argument('--selector',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cover-deaths',action='store_true',help='Close macro states under accidental advancement; do not optimize over death edges')
    a=p.parse_args();started=time.monotonic();native=json.loads(a.selector.read_text())
    for n,h in native['sources'].items():
        if hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest()!=h:raise ValueError('Selector source changed: '+n)
    result=compose(rom_tables.load(a.rom,'dle21'),native,cover_deaths=a.cover_deaths)
    verify(result)
    result.update(rom_sha256=native['rom_sha256'],selector_sha256=hashlib.sha256(a.selector.read_bytes()).hexdigest(),
                  seconds=time.monotonic()-started,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  sources={n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in
                           ('dle_scheduler_graph.py','dle_retry_rules.py','rom_controls.py','cine_room_optimality.py','verify_dl1_scheduler.py','rom_tables.py','rom_proof.py')})
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,separators=(',',':'))+'\n')
    print(len(result['states']),'macro states; initial',result['initial'],'all Nature alternatives have equal values')


if __name__=='__main__':main()
