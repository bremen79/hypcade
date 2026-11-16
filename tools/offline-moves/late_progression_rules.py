#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""E/F canonical single-player progression contracts for the factored proof.

Three passes follow from next-group exits and the final descriptor's fixed
descending exhaustion. The two intermissions explicitly return to group one;
the dragon wins. Recovery bypasses preserve these histories. This does not
model arbitrary Android delivery phases or the original cross-player alias.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

import cine_room_optimality
import dl1_selector
import late_order_invariance
import late_retry_rules
import rom_kernel
import rom_proof
import rom_tables
import verify_dl1_scheduler

ROOT=Path(__file__).resolve().parent


def verify_itinerary(groups,scene,history,pending=False):
    """Check the reachable history shape without expanding its Cartesian product.

    Variant identities stay literal. Only their population counts are used to
    establish the three-pass itinerary; values still depend on actual masks.
    """
    if len(history)!=13 or any(not 0<=m<=7 for m in history):raise ValueError('Invalid itinerary history')
    if pending:
        if any(m!=7 for m in history):raise ValueError('Pending playback precedes final selection')
        return 'pending'
    if scene==0:
        if any(history):raise ValueError('Noninitial bridge history')
        return 'initial'
    owners=[g for g,roots in groups.items() if scene in roots]
    if len(owners)!=1:raise ValueError('Room does not identify a unique logical group')
    group=owners[0]
    if not any(root==scene and history[group-1]&(1<<i) for i,root in enumerate(groups[group])):
        raise ValueError('Current variant is not selected')
    final=history[12]
    if group==13:
        expected={62:4,72:6,78:7}.get(scene)
        if final!=expected:raise ValueError('Wrong final-room exhaustion order')
        lap=final.bit_count()
        if any(m.bit_count()!=lap for m in history[:12]):raise ValueError('Final room has incomplete preceding pass')
    else:
        if final not in (0,4,6):raise ValueError('Regular room after the third final selection')
        lap=final.bit_count()+1
        for g,mask in enumerate(history[:12],1):
            if mask.bit_count()!=(lap if g<=group else lap-1):raise ValueError('History does not follow the current pass')
    return 'lap%d-group%d'%(lap,group)


def initialize(ram):
    if len(ram)!=1024:raise ValueError('Expected complete board RAM')
    out=bytearray(ram);out[48]=out[24];out[49]=out[21]
    out[50:56]=bytes(6);out[0xc0:0xc8]=bytes(8);out[0x60:0x90]=bytes(48)
    if not out[16]&16:out[9]=(out[9]-1)&255
    out[8]&=95
    return out


def resume_selector(ram,player):
    if len(ram)!=1024 or player not in (0x30,0x38):raise ValueError('Expected board RAM and player')
    out=bytearray(ram)
    if out[16]&8:raise ValueError('Alternate start bank outside progression contract')
    if not out[18]&128 or out[player+5]&32:return out
    if not out[player+5]&128 or out[player+5]&64:raise ValueError('Fresh selection requires the complete selector')
    out[0x54]=out[18]&127;out[player+6]=out[18]&127
    return out


def audit(rom,game,build):
    if game not in late_retry_rules.PCS:raise ValueError('Expected E/F ROM')
    kernel=rom_kernel.Kernel(rom,build);pc=late_retry_rules.PCS[game]
    init,stop=(0x12cd,0x130e) if game=='lair_e' else (0x133a,0x137b)
    counts=dict(initialize=0,resume_selector=0,fresh_selector=0,assign=0)
    for value in range(256):
      for free in (0,16):
        ram=bytearray([value]*1024);ram[16]=free;ram[24]=128;ram[21]=197
        out,_=kernel.call(ram,init,stop=stop)
        if out[:0x3d0]!=initialize(ram)[:0x3d0]:raise ValueError('Fresh game does not clear the modeled history/queue')
        counts['initialize']+=1
    for player in (0x30,0x38):
      for raw in range(256):
        for flags in (0,32,128,136,160,192,255):
            if raw&128 and not flags&32 and (not flags&128 or flags&64):continue
            ram=bytearray([37]*1024);ram[16]=38;ram[18]=raw;ram[player+5]=flags
            expected=resume_selector(ram,player)
            out,regs=kernel.call(ram,pc['selector'],de=0xa000+player)
            if out[:0x3d0]!=expected[:0x3d0] or regs['observations']:raise ValueError('Restart changes history or reruns random selection')
            counts['resume_selector']+=1
    # Exercise the actual full prelude, not only the mask dispatcher. Fresh
    # deaths may enter at step one, but the room entry values are equal.
    desc=verify_dl1_scheduler.descriptors(rom,game)
    for player in (0x30,0x38):
      history_base=0x60 if player==0x30 else 0x90
      for group in range(1,14):
        for mask in ((0,4,6) if group==13 else range(7)):
          for flags in (0,64,192):
            ram=bytearray(1024);ram[16]=54;ram[17]=88;ram[18]=group|128
            ram[player+5]=flags;ram[history_base+group]=mask
            for seed in range(128):
                out,regs=kernel.call(ram,pc['selector'],de=0xa000+player,refresh=seed)
                after=out[history_base+group];changed=after^mask
                if not changed or changed&(changed-1) or mask&changed:
                    raise ValueError('Fresh selector did not consume exactly one unused variant: %s player=%x group=%d mask=%d flags=%d seed=%d after=%d root=%d' %
                        (game,player,group,mask,flags,seed,after,out[14]))
                choice=changed.bit_length()-1
                if choice not in range(3) or out[14]!=(desc[group]['scenes'][choice]+42)|128:
                    raise ValueError('Fresh selector changed the fixed harder-version multiset')
                if out[15]!=int(bool(flags&64)) or out[player+5]!=(flags&191) or out[player+6]!=group:
                    raise ValueError('Fresh retry prelude did not preserve its entry/episode contract')
                if group==13 and choice!={0:2,4:1,6:0}[mask]:raise ValueError('Final descriptor can reorder the dragon')
                for g in range(1,14):
                    if g!=group and out[history_base+g]!=ram[history_base+g]:raise ValueError('Selector changes another group history')
                counts['fresh_selector']+=1
    assign_pc=0x1ab4 if game=='lair_e' else 0x1be9
    for raw in range(256):
      for physical in (128,158,190,206,221):
        ram=bytearray(1024);ram[18]=raw;ram[8]=255;ram[0x202]=physical
        expected=bytearray(ram);late_retry_rules.assign(expected,0x200)
        out,_=kernel.call(ram,assign_pc)
        if out[:0x3d0]!=expected[:0x3d0]:raise ValueError('Physical record assignment changed')
        counts['assign']+=1
    model=cine_room_optimality.Model(rom,game);graph=model.graph();values=rom_proof.solve(graph)
    index={s:u for u,s in enumerate(graph['states'])}
    roots={s+42 for d in desc.values() for s in d['scenes']}
    effects,_=verify_dl1_scheduler.room_effects(model,graph,roots|{0})
    for scene in roots|{0}:
        want={('win',)} if scene==78 else {('explicit',1)} if scene in (62,72) else {('next',)}
        if effects[index[scene,0]]!=want:raise ValueError('A surviving room can change the three-pass itinerary')
    todo=[index[0,0]];seen=set(todo)
    for u in todo:
        if graph['awards'][u] or any(label[0] for label,_ in graph['actions'][u]):raise ValueError('Initial bridge has a decision or award')
        for _,targets in graph['actions'][u]:
            for v in targets:
                if v not in seen:seen.add(v);todo.append(v)
    if not model.won(graph['states'][todo[-1]]):raise ValueError('Initial bridge does not finish automatically')
    return dict(game=game,rom_sha256=hashlib.sha256(rom).hexdigest(),native_cases=counts,
        total_cases=sum(counts.values()),operator_levels=[0,1],
        symbolic_progression=['Zero-cost automatic bridge selects group one with empty histories/queue',
            'Each regular survivor or deferred death advances one logical group',
            'Each selection consumes one fresh variant; fixed versions make phases irrelevant to suffix values',
            'Final group selects intermission 62, intermission 72, then dragon 78',
            'Intermissions explicitly return to group one; only the dragon wins',
            'Queued playback bypasses selection; immediate retries preserve histories',
            'A queued-room death re-appends its consumed room without changing any history',
            'Empty drain restores the already-selected dragon; no fourth normal pass'],
        symbolic_rank='Every fresh selection consumes one of 39 variant bits; only two final intermission returns precede the winning dragon. Pending completions consume queued rooms; local decisions follow their checked DAG. Deaths are external.',
        scope='Single-player canonical-mask macro progression; composes with separately audited retry and factor contracts',
        limits='Not a cross-player alias proof or universal acceptance/delivery proof')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--roms',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    started=time.monotonic();cases=[]
    for game in late_retry_rules.PCS:
        cases.append(audit(rom_tables.load(a.roms/(game+'.zip'),game),game,a.output/'build'))
        print(game,cases[-1]['native_cases'],flush=True)
    result=dict(cases=cases,seconds=time.monotonic()-started,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        sources={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in
            ('late_progression_rules.py','late_retry_rules.py','cine_room_optimality.py','verify_dl1_scheduler.py','rom_proof.py','rom_tables.py','rom_kernel.py','rom_kernel.c')})
    (a.output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
