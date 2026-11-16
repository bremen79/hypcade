#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact US DL1 selector-support allocation without a room-permutation graph.

This solves the relaxation where each selector entry can observe any audited
refresh phase. It is an attainable game optimum only after physical timing
witnesses establish those observations. It is never an expectation by default.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

import cine_room_optimality
import rom_proof
import rom_tables
import rom_kernel
import dl1_selector


def support(selector, enabled=True):
    return {(r['used'], r['mask']): sorted({tuple(p[:3]):seed for seed,p in
            enumerate(r['phases'])}.items()) for r in selector['transitions'] if r['enabled']==enabled}


def costs(model, graph, values, objective):
    index = {tuple(s):u for u,s in enumerate(graph['states'])}
    answer = {}
    for scene in range(model.spec['count']):
        if (scene,0) not in index:
            continue
        u = index[scene,0]
        m,s = ((values['fewest'][u], values['score_at_fewest'][u]) if objective=='shortest'
               else (values['fewest_at_score'][u], values['highest_score'][u]))
        if m is not None:
            answer[scene] = (m,-s) if objective=='shortest' else (-s,m)
    return answer


def add(*pairs):
    return tuple(sum(p[i] for p in pairs) for i in (0,1))


def allocate(groups, transitions, room_costs, normal_groups, offset=40, first_choice=None, boundaries=range(32)):
    """Two monotone five-bit resource streams, joined at the lap boundary.

    Fix U, the optional rooms used after lap two. Process group g's lap-two
    and lap-three choices together, starting the two streams at 0 and U.
    Require lap two ends at U. This commutes only independent group work;
    both streams retain their original order and correlated selector support.
    """
    best = None
    total_states = 0
    peak_states = 0
    for boundary in boundaries:
        states = {(0,boundary): ((0,0), ())}
        for group_number, group in enumerate(groups):
            following = {}
            for (used2,used3), (value,witness) in states.items():
                for first in range(3):
                    if group_number==0 and first_choice is not None and first!=first_choice:
                        continue
                    root1 = group[first] + (0 if group_number<normal_groups else offset)
                    for (second,mask2,next2),phase2 in transitions[used2,1<<first]:
                        if next2 & ~boundary:
                            continue
                        root2 = group[second]+offset if second<3 else 80+second-3
                        for (third,mask3,next3),phase3 in transitions[used3,mask2]:
                            root3 = group[third]+offset if third<3 else 80+third-3
                            candidate = add(value,room_costs[root1],room_costs[root2],room_costs[root3])
                            key = next2,next3
                            if key not in following or candidate < following[key][0]:
                                row = dict(group=group_number+1, first=first, second=second, third=third,
                                    roots=[root1,root2,root3], phase2=phase2, phase3=phase3,
                                    used2_before=used2, used3_before=used3, used2_after=next2,
                                    used3_after=next3, mask_after_second=mask2, mask_after_third=mask3)
                                following[key] = candidate, witness+(row,)
            states = following
            peak_states = max(peak_states,len(states))
            total_states += len(states)
        for (used2,used3),(value,witness) in states.items():
            if used2==boundary and (best is None or value<best['value']):
                best = dict(value=value, boundary=boundary, final_used=used3, groups=witness)
    if best is None:
        raise ValueError('No feasible selector allocation')
    best.update(total_dp_states=total_states, peak_dp_states=peak_states)
    return best


def verify_witness(result, groups, transitions, room_costs, normal_groups, offset=40):
    used2,used3 = 0,result['boundary']
    total = (0,0)
    for i,row in enumerate(result['groups']):
        first,second,third = (row[k] for k in ('first','second','third'))
        expected2 = next(((choice,mask,used) for (choice,mask,used),seed in transitions[used2,1<<first]
                          if choice==second and seed==row['phase2']),None)
        if expected2 is None: raise ValueError('Invalid second-visit selector witness')
        _,mask,used2 = expected2
        expected3 = next(((choice,mask,used) for (choice,mask,used),seed in transitions[used3,mask]
                          if choice==third and seed==row['phase3']),None)
        if expected3 is None: raise ValueError('Invalid third-visit selector witness')
        _,_,used3 = expected3
        roots = [groups[i][first]+(0 if i<normal_groups else offset),
                 groups[i][second]+offset if second<3 else 80+second-3,
                 groups[i][third]+offset if third<3 else 80+third-3]
        if roots!=row['roots']: raise ValueError('Incorrect version/room allocation')
        total = add(total,*(room_costs[r] for r in roots))
    if used2!=result['boundary'] or used3!=result['final_used'] or total!=tuple(result['value']):
        raise ValueError('Allocation resource boundary or reward mismatch')


def allocate_three(groups,first_tables,later,room_costs,normal_groups,offset=40,boundaries=range(32),first_choice=None,known=None):
    """Exact three-pass resource join when a first visit may also inject.

    U and V are optional-resource masks after visits one and two. For fixed
    U subset V, interleave independent groups while preserving the order in
    each visit stream. No full history-mask Cartesian product is constructed.
    """
    known={} if known is None else known
    if any(lap not in (0,1,2) or not 0<=group<len(groups) for lap,group in known):
        raise ValueError('Observed allocation index outside the three passes')
    first_extra=any(c>=3 for table in first_tables for used in boundaries
                    for (c,_,_),_ in table[used,0])
    best=None;count=peak=0
    for boundary1 in boundaries if first_extra else (0,):
        for boundary2 in boundaries:
            if boundary1&~boundary2:continue
            states={(0,boundary1,boundary2):((0,0),())}
            for g,group in enumerate(groups):
                following={}
                def root(choice,lap):
                    return 80+choice-3 if choice>=3 else group[choice]+(0 if lap==0 and g<normal_groups else offset)
                def allowed(lap,choice,mask,used):
                    observed=known.get((lap,g))
                    return observed is None or (root(choice,lap),mask,used)==(
                        observed['scene'],observed['mask'],observed['used'])
                for (used1,used2,used3),(value,witness) in states.items():
                    for (first,mask1,next1),phase1 in first_tables[g][used1,0]:
                        if g==0 and first_choice is not None and first!=first_choice:continue
                        if next1&~boundary1:continue
                        if not allowed(0,first,mask1,next1):continue
                        for (second,mask2,next2),phase2 in later[used2,mask1]:
                            if next2&~boundary2:continue
                            if not allowed(1,second,mask2,next2):continue
                            for (third,mask3,next3),phase3 in later[used3,mask2]:
                                if not allowed(2,third,mask3,next3):continue
                                roots=[root(first,0),root(second,1),root(third,2)]
                                candidate=add(value,*(room_costs[r] for r in roots))
                                key=next1,next2,next3
                                if key not in following or candidate<following[key][0]:
                                    row=dict(group=g+1,first=first,second=second,third=third,roots=roots,
                                             phase1=phase1,phase2=phase2,phase3=phase3,
                                             mask_after_first=mask1,mask_after_second=mask2,mask_after_third=mask3)
                                    following[key]=candidate,witness+(row,)
                states=following;peak=max(peak,len(states));count+=len(states)
                if not states:break
            for (used1,used2,used3),(value,witness) in states.items():
                if used1==boundary1 and used2==boundary2 and (best is None or value<best['value']):
                    best=dict(value=value,boundary1=boundary1,boundary=boundary2,final_used=used3,groups=witness)
    if best is None:raise ValueError('No feasible three-visit allocation')
    best.update(total_dp_states=count,peak_dp_states=peak)
    return best


def verify_three(result,first_tables,later,room_costs,groups,normal_groups,offset=40):
    used=[0,result['boundary1'],result['boundary']];total=(0,0)
    for g,row in enumerate(result['groups']):
        mask=0
        for lap,name in enumerate(('first','second','third')):
            table=first_tables[g] if lap==0 else later
            phase=row['phase%d'%(lap+1)]
            matches=[(c,m,u) for (c,m,u),seed in table[used[lap],mask] if c==row[name] and seed==phase]
            if len(matches)!=1:raise ValueError('Invalid three-visit witness')
            _,mask,used[lap]=matches[0]
            if mask!=row['mask_after_'+name]:raise ValueError('Witness history mismatch')
            choice=row[name]
            root=80+choice-3 if choice>=3 else groups[g][choice]+(0 if lap==0 and g<normal_groups else offset)
            if root!=row['roots'][lap]:raise ValueError('Witness physical room/version mismatch')
            total=add(total,room_costs[row['roots'][lap]])
    if used!=[result['boundary1'],result['boundary'],result['final_used']] or total!=tuple(result['value']):
        raise ValueError('Three-visit resource boundary or reward mismatch')


def audit_scheduler(rom, entry, result, normal_groups, kernel):
    """Replay allocation chronologically through the original descriptor loader.

    Calls the original selector and version/physical-step routing together.
    Phase is an explicit routine input; no physical delivery claim is made.
    """
    signature = rom.find(bytes.fromhex('3a54a0856f2255a0'))
    if signature < 15 or rom[signature-15:signature-12] != bytes.fromhex('d93e30'):
        raise ValueError('Unknown complete group selector')
    pc = signature-15
    ram = bytearray(1024)
    transcript=[]
    for lap in range(3):
        for group in range(1,14):
            desc=entry['descriptors'][str(group)]
            # Recover the actual ROM pointer, not a synthetic selector array.
            reference=rom.find(bytes.fromhex('3a54a0cb27cb27'))
            descriptors=rom_tables.word(rom,reference-2)
            pointer=rom_tables.word(rom,descriptors+4*group)
            ram[0x50:0x52]=pointer.to_bytes(2,'little')
            ram[0x52:0x55]=bytes((desc['flags'],desc['mask'],group))
            hard=lap>0 or group>normal_groups
            ram[0x35]=16 if hard else 0
            ram[0x10]=(2 if entry['game'] in ('lair_e','lair_f') else 0) | (4 if normal_groups==0 else 0)
            ram[0x11]=8
            if group==13:
                wanted=desc['scenes'][2-lap]+(42 if entry['game'] in ('lair_e','lair_f') else 40)
                expected_mask=(4,6,7)[lap]
            else:
                row=result['groups'][group-1]
                wanted=row['roots'][lap]
                expected_mask=(row['mask_after_first'],row['mask_after_second'],row['mask_after_third'])[lap]
            observed=[]
            for seed in range(8):
                out,info=kernel.call(ram,pc,refresh=seed)
                observed.append((seed,out[14]&127,out[0x60+group]&7,out[0x35]))
                if out[14]&127==wanted and out[0x60+group]&7==expected_mask:
                    break
            else:
                raise ValueError('Allocation cannot occur under the original group selector: lap=%d group=%d root=%d mask=%d actual=%r' % (lap,group,wanted,expected_mask,observed))
            if out[15]!=0:raise ValueError('Unexpected physical retry step')
            transcript.append(dict(lap=lap,group=group,root=wanted,seed=seed,
                observed_refresh=info['observations'],mask=expected_mask))
            ram=out
    actual_used=sum(bool(ram[0x70+i])<<i for i in range(5)) if entry['game'] not in ('lair_e','lair_f') else 0
    if actual_used!=result['final_used']:
        raise ValueError('Full selector optional-room flags differ from allocation')
    return dict(entry_pc=pc,cases=len(transcript),transcript=transcript,
                scope='Original descriptor selection and version routing; explicit refresh seeds, not physical input timing')


def analyze(roms, scheduler_path, output, first_choice=None, reuse_selectors=None):
    output.mkdir(parents=True,exist_ok=True)
    started = time.monotonic()
    scheduler = json.loads(scheduler_path.read_text())
    cached=json.loads(reuse_selectors.read_text()) if reuse_selectors else None
    if cached:
        for name in ('dl1_selector.py','rom_kernel.py','rom_kernel.c'):
            if hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()!=cached['sources'][name]:
                raise ValueError('Cached selector source changed: '+name)
    reports=[]
    for entry in scheduler['cases']:
        game = entry['game']
        if game not in ('lair_a','lair_b','lair_c','lair_d','lair_e','lair_f'):
            continue
        rom=rom_tables.load(roms/(game+'.zip'),game)
        if hashlib.sha256(rom).hexdigest()!=entry['rom_sha256']:
            raise ValueError('Selector belongs to another ROM')
        model=cine_room_optimality.Model(rom,game)
        graph=model.graph();values=rom_proof.solve(graph)
        groups=[entry['descriptors'][str(i)]['scenes'] for i in range(1,13)]
        extra=game not in ('lair_e','lair_f')
        boundaries=range(32) if extra else (0,)
        offset=40 if extra else 42
        if extra and list(rom[0x38af:0x38b4])!=list(range(208,213)):
            raise ValueError('Unrecognized optional-room identities')
        rows=[]
        kernel=rom_kernel.Kernel(rom,output/'build')
        tables={};audits=[]
        cached_game=next((r for r in cached['cases'] if r['game']==game),None) if cached else None
        if cached_game:
            if cached_game['rom_sha256']!=entry['rom_sha256']:raise ValueError('Cached selector ROM changed')
            for saved in cached_game['selector_tables']:
                tables[saved['raw_hard'],saved['hard']]={(r['used'],r['mask']):[(tuple(v),seed) for v,seed in r['support']] for r in saved['rows']}
            audits=cached_game['selector_audits']
        else:
            for raw_hard,hard in ((False,False),(False,True),(True,True)):
                tables[raw_hard,hard],audit=dl1_selector.extract(rom,game,kernel,raw_hard,hard)
                audits.append(audit)
        for objective in ('shortest','highest-score'):
            room_costs=costs(model,graph,values,objective)
            for difficulty,normal_groups in enumerate((0,0,4,8)):
                raw=normal_groups==0
                first_tables=[tables[raw,g>=normal_groups] for g in range(12)]
                later=tables[raw,True]
                result=allocate_three(groups,first_tables,later,room_costs,normal_groups,offset=offset,boundaries=boundaries,first_choice=first_choice)
                verify_three(result,first_tables,later,room_costs,groups,normal_groups,offset)
                native=audit_scheduler(rom,entry,result,normal_groups,kernel)
                # Group thirteen is fixed descending: hub, intermediate, dragon.
                final=entry['descriptors']['13']['scenes'][::-1]
                total=add(result['value'],*(room_costs[s+offset] for s in final))
                m,s = (total[0],-total[1]) if objective=='shortest' else (total[1],-total[0])
                row=dict(difficulty=difficulty,objective=objective,inputs=m,score=s,
                         allocation=result,final_group=final,native_scheduler=native)
                rows.append(row)
                print(game,objective,difficulty,m,s,'peak states',result['peak_dp_states'],flush=True)
        saved_tables=[dict(raw_hard=raw,hard=hard,rows=[dict(used=u,mask=m,support=rows) for (u,m),rows in table.items()])
                      for (raw,hard),table in tables.items()]
        reports.append(dict(game=game,rom_sha256=entry['rom_sha256'],results=rows,selector_audits=audits,selector_tables=saved_tables))
    sources={n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in
             ('dl1_allocation.py','dl1_selector.py','cine_room_optimality.py','rom_proof.py','rom_tables.py','rom_kernel.py','rom_kernel.c')}
    report=dict(cases=reports,sources=sources,selector_report_sha256=hashlib.sha256(scheduler_path.read_bytes()).hexdigest(),
                seconds=time.monotonic()-started,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                initial_choice=first_choice,reused_selectors=str(reuse_selectors) if reuse_selectors else None,
                interpretation='Exact selector-support control relaxation; no probability law; physical phase attainability not yet proved')
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--roms',type=Path,required=True)
    p.add_argument('--scheduler',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--initial-choice',type=int,choices=range(3))
    p.add_argument('--reuse-selectors',type=Path)
    a=p.parse_args();analyze(a.roms,a.scheduler,a.output,a.initial_choice,a.reuse_selectors)


if __name__=='__main__':main()
