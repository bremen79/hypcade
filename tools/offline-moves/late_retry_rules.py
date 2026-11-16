#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""E/F life/restart/queue rules, retaining original unpatched behavior.

Deaths are external observations, never optimization actions. In particular,
dying in a queued replay re-appends that room; do not borrow DLE21's patch.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

import cine_room_optimality
import rom_kernel
import rom_proof
import rom_tables
import verify_dl1_scheduler

ROOT=Path(__file__).resolve().parent
PCS={
 'lair_e':dict(append=0x1dbd,drain=0x1e29,dispatch=0x1ddf,advance=0x1da3,
    life=0x1459,life_stop=0x14ac,restart=0x13b0,restart_stop=0x13e3,selector=0x1b8e),
 'lair_f':dict(append=0x1ef2,drain=0x1f5e,dispatch=0x1f14,advance=0x1ed8,
    life=0x14c6,life_stop=0x1519,restart=0x141d,restart_stop=0x1450,selector=0x1cc3),
}
FLUSH=frozenset((0xa4,0xce))


def checked(ram,player,footer):
    if len(ram)!=1024 or player not in (0x30,0x38) or not 0<=footer<=1016:
        raise ValueError('Expected complete RAM, player slot and footer')


def assign(out,footer):
    raw=out[18]
    if raw&128:out[14]=raw;out[15]=0;out[8]&=254
    else:out[15]=raw;out[14]=out[footer+2]


def append(ram,player=0x30,footer=0x200):
    checked(ram,player,footer);out=bytearray(ram)
    for slot in range(player+0x90,player+0x98):
        if out[slot]:continue
        bonus=bool(out[player+5]&2);out[player+5]&=253
        out[slot]=(out[footer+2]+5*bonus)&255
        break
    return out


def finish_death(out,player):
    death=bool(out[player+5]&128);out[player+5]&=127
    if death:out[15]=1
    return out


def drain(ram,player=0x30,footer=0x200):
    checked(ram,player,footer);out=bytearray(ram)
    slot=next((i for i in range(player+0x90,player+0x98) if out[i]),None)
    if slot is None:
        out[18]=out[player+0xa0]
        # Literal original shadow write. This is not the active episode at
        # player+6, and differs from the authored DLE patch's player+56h.
        out[player+0x30]=out[player+0xa1]
        out[player+5]=(out[player+5]|12)&159
    else:out[18]=out[slot];out[slot]=0
    assign(out,footer)
    return finish_death(out,player)


def dispatch(ram,player=0x30,footer=0x200):
    checked(ram,player,footer);out=bytearray(ram)
    if not out[18]&128:return out
    if not out[player+5]&8:
        if out[player+5]&32:return drain(out,player,footer)
        if out[18] in FLUSH:
            if out[17]&32:raise ValueError('Alternate scoring bank outside dispatcher contract')
            out[player+5]|=32
            out[player+0xa0]=out[18];out[player+0xa1]=out[player+6]
            return drain(out,player,footer)
    return finish_death(out,player)


def advance(ram,player=0x30,footer=0x200):
    checked(ram,player,footer);out=bytearray(ram)
    if out[18]&128 and not out[footer+5]&2:
        out[18]=((out[player+6]+1)&255)|128;assign(out,footer)
    return out


def life(ram,player=0x30,footer=0x200):
    checked(ram,player,footer)
    if ram[16]&8 or ram[17]&4:raise ValueError('Alternate life bank outside supported contract')
    out=bytearray(ram);out[player+5]|=128
    if not out[footer+5]&4:
        out[player+5]|=64
        out=append(out,player,footer)  # Also during pending-room playback.
        if not out[player+5]&32:out[footer+2]=((out[player+6]+1)&255)|128
    out[player+5]&=253;out[player]=out[footer+2]
    if not out[10]&1:out[player+1]=(out[player+1]-1)&255
    return out


def restart(ram,player=0x30,footer=0x200):
    checked(ram,player,footer);out=bytearray(ram)
    out[player+7]=0
    fresh=bool(out[player+1]&64 or out[player+5]&64);out[player+1]&=191
    out[18]=out[player];assign(out,footer)
    if not fresh:out[15]=1
    return out


def room_invariants(rom,game):
    model=cine_room_optimality.Model(rom,game);graph=model.graph();values=rom_proof.solve(graph)
    index={s:i for i,s in enumerate(graph['states'])};desc=verify_dl1_scheduler.descriptors(rom,game)
    roots=sorted({s+offset for d in desc.values() for s in d['scenes'] for offset in (0,42)})
    immediate={20,30,36,62,72,78};pending=[];fatal=0
    effects,_=verify_dl1_scheduler.room_effects(model,graph,set(roots))
    for scene in roots:
        if any(values[k][index[scene,0]]!=values[k][index[scene,1]] for k in values):
            raise ValueError('Retry entry changes a room value')
        todo=[index[scene,0],index[scene,1]];seen=set(todo);deaths=[]
        for u in todo:
            r=model.record_for(graph['states'][u])
            if r['death']:deaths.append(r);fatal+=1
            for _,targets in graph['actions'][u]:
                for v in targets:
                    if v not in seen:seen.add(v);todo.append(v)
        if any(bool(r['trailer'][4]&4)!=(scene in immediate) for r in deaths):
            raise ValueError('Unexpected immediate/delayed death class')
        if scene in immediate:
            expected={('win',)} if scene in (36,78) else {('explicit',1)}
            if effects[index[scene,0]]!=expected:raise ValueError('Immediate retry has episode-dependent exit')
        elif deaths:
            if effects[index[scene,0]]!={('next',)}:raise ValueError('Pending room changes the logical itinerary')
            pending.append(dict(scene=scene,values={k:values[k][index[scene,0]] for k in values}))
    return dict(selectable_roots=roots,root_zero_one_values_equal=True,
        immediate_roots=sorted(immediate),pending_rooms=pending,fatal_records=fatal,
        pending_exit='next, intercepted by active queue dispatcher',
        immediate_exit='explicit episode one at intermissions, or successful dragon end; no increment of overwritten episode')


def audit(rom,game,build):
    kernel=rom_kernel.Kernel(rom,build);pc=PCS[game];counts={k:0 for k in ('append','drain','dispatch','advance','life','restart','selector_bypass')}
    def verify(ram,player,kind):
        expected=globals()[kind](ram,player)
        stop=pc[kind+'_stop'] if kind in ('life','restart') else 0xdead
        actual,regs=kernel.call(ram,pc[kind],stop=stop,de=0xa000+player,refresh=127)
        if actual[:0x3d0]!=expected[:0x3d0] or regs['observations']:
            diff=[hex(i) for i in range(0x3d0) if actual[i]!=expected[i]]
            raise ValueError('Original E/F retry primitive differs: %s %s %s'%(game,kind,diff))
        reads,writes=kernel.access()
        allowed={8,10,14,15,16,17,18,player,player+1,player+5,player+6,player+7,player+0x30,
            player+0xa0,player+0xa1,0x202,0x205,*range(player+0x90,player+0x98)}
        if any(i<0x3d0 and i not in allowed for i in reads|writes):raise ValueError('Retry primitive accesses undeclared state')
        counts[kind]+=1
    for player in (0x30,0x38):
        for occupied in range(9):
          for raw in range(256):
            for bonus in (0,2):
                ram=bytearray(1024);ram[player+5]=bonus|0x50;ram[0x202]=raw
                ram[player+0x90:player+0x90+occupied]=bytes(range(129,129+occupied));verify(ram,player,'append')
        for mask in range(256):
          for flags in (0,8,32,64,128,160,192,255):
            for saved in sorted(FLUSH):
                ram=bytearray(1024);ram[8]=255;ram[player+5]=flags;ram[18]=saved
                ram[player+6]=13;ram[player+0xa0]=saved;ram[player+0xa1]=13
                for slot in range(8):ram[player+0x90+slot]=129+slot if mask&(1<<slot) else 0
                verify(ram,player,'drain');verify(ram,player,'dispatch')
        for outcome in (0,1,127,128,143,164,206,255):
          for flags in range(256):
            ram=bytearray(1024);ram[8]=255;ram[18]=outcome;ram[player+5]=flags
            ram[player+6]=13;ram[player+0xa0]=206;ram[player+0xa1]=13;ram[player+0x90]=155
            verify(ram,player,'dispatch')
        for outcome in range(256):
          for episode in (0,1,12,13,20,30,36,62,72,78,127,255):
            for effect in (0,2):
                ram=bytearray(1024);ram[18]=outcome;ram[0x205]=effect;ram[player+6]=episode;ram[8]=255
                verify(ram,player,'advance')
        for raw in range(128,222):
          for flags in (0,2,8,32,34,64,128,160,255):
            for effect in (0,4):
                ram=bytearray(1024);ram[16]=38;ram[17]=216;ram[player+1]=133
                ram[player+5]=flags;ram[player+6]=13;ram[0x202]=raw;ram[0x205]=effect
                ram[player+0x90]=145;verify(ram,player,'life')
          for flags in (0,32,64,128,192,255):
            for lives in (1,5,64,65,128,255):
                ram=bytearray(1024);ram[8]=255;ram[player]=raw;ram[player+1]=lives
                ram[player+5]=flags;ram[player+7]=9;verify(ram,player,'restart')
        for raw in range(256):
            ram=bytearray(1024);ram[16]=38;ram[17]=216;ram[18]=raw;ram[player+5]=32
            actual,regs=kernel.call(ram,pc['selector'],de=0xa000+player)
            if actual[:0x3d0]!=ram[:0x3d0] or regs['observations']:raise ValueError('Pending room reruns logical selector')
            counts['selector_bypass']+=1
    return dict(game=game,native_cases=counts,total_cases=sum(counts.values()),
        room_invariants=room_invariants(rom,game),rom_sha256=hashlib.sha256(rom).hexdigest(),
        scope='Life-prefix, restart, advance, queue, dispatcher and pending-selector contracts; physical recovery composition remains separate')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--roms',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    start=time.monotonic();cases=[]
    for game in PCS:
        cases.append(audit(rom_tables.load(a.roms/(game+'.zip'),game),game,a.output/'build'))
        print(game,cases[-1]['total_cases'],flush=True)
    result=dict(cases=cases,seconds=time.monotonic()-start,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        sources={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
            ('late_retry_rules.py','cine_room_optimality.py','rom_tables.py','rom_proof.py','verify_dl1_scheduler.py','rom_kernel.py','rom_kernel.c')})
    (a.output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
