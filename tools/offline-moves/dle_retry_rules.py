#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""DLE21's pending-room primitives, transcribed from original ROM code.

The ROM's queue has eight physical slots and may contain holes. This module
retains their exact order/state for native checking. Additive objective
reduction is separate from proving complete life-loss/dispatch composition.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

import cine_room_optimality
import rom_controls
import rom_kernel
import rom_proof
import rom_tables
import verify_dl1_scheduler

APPEND=0x1ef2
DRAIN=0x1f5e
BEGIN=0x1f4e
DISPATCH=0x1f14
LIFE=0x14c6
RESTART=0x1423
EXCLUDED=frozenset((0xb2,0xe5,0x94,0xc7,0x95,0xc8))
FLUSH=frozenset((0xa6,0xa8,0xaa,0xa4,0xd9,0xdb,0xdd,0xd7))


def checked(ram,player):
    if len(ram)!=1024 or player not in (0x30,0x38):raise ValueError('Expected complete RAM and a player slot')


def append(ram,player=0x30,footer=0x200):
    """1EF2: first empty physical slot; full queue drops this insertion."""
    checked(ram,player)
    if not 0<=footer<=1016:raise ValueError('Invalid footer address')
    out=bytearray(ram)
    for slot in range(player+0x90,player+0x98):
        if out[slot]:continue
        raw=out[footer+2]
        bonus=bool(out[player+5]&2);out[player+5]&=253
        raw=(raw+5*bonus)&255
        if raw not in EXCLUDED:out[slot]=raw
        break
    return out


def drain(ram,player=0x30):
    """1F5E: pop one queued room, or restore the suspended boundary.

    Queue/saved scene bytes must be encoded physical roots. The current
    logical episode is untouched. Preserve the ROM's literal write at
    player+0x56 when restoring its saved episode; do not reinterpret it as
    player+6. That shadow write is outside the active history mask array.
    """
    checked(ram,player);out=bytearray(ram)
    queue=out[player+0x90:player+0x98]
    if any(v and not 128<=v<234 for v in queue):raise ValueError('Unencoded pending physical root')
    slot=next((i for i,v in enumerate(queue) if v),None)
    if slot is None:
        raw=out[player+0xa0]
        if raw not in FLUSH:raise ValueError('Unknown saved DLE boundary')
        if raw in (0xa4,0xd7):out[player+5]|=4
        else:out[8]|=2
        out[player+0x56]=out[player+0xa1]
        out[player+5]=(out[player+5]|8)&159
    else:
        raw=queue[slot];out[player+0x90+slot]=0
    out[0x12]=raw;out[14]=raw;out[15]=0;out[8]&=254
    death=bool(out[player+5]&128);out[player+5]&=127
    if death:out[15]=1
    return out


def begin(ram,player=0x30):
    checked(ram,player);out=bytearray(ram)
    if out[0x12] not in FLUSH:raise ValueError('Unknown DLE flush boundary')
    out[player+0xa0]=out[0x12];out[player+0xa1]=out[player+6]
    return drain(out,player)


def dispatch(ram,player=0x30,footer=0x200):
    """1F14, including the DLE flush patch and death's step-one override."""
    checked(ram,player)
    if not 0<=footer<=1016:raise ValueError('Invalid footer address')
    out=bytearray(ram)
    if not out[0x12]&128:return out
    if not out[player+5]&8:
        if out[player+5]&32:return drain(out,player)
        if out[0x12] in FLUSH:
            out[footer+5]&=127;out[8]&=253;out[player+5]|=32
            return begin(out,player)
    death=bool(out[player+5]&128);out[player+5]&=127
    if death:out[15]=1
    return out


def life(ram,player=0x30,footer=0x200):
    """14C6–1519 under the supported banks, before score-display refresh."""
    checked(ram,player)
    if not 0<=footer<=1016:raise ValueError('Invalid footer address')
    if ram[0x10]!=50 or ram[0x11]!=216:raise ValueError('Unsupported DLE operator banks')
    out=bytearray(ram)
    if out[player+5]&32:out[footer+5]&=127;out[8]&=253
    out[player+5]|=128
    if not out[footer+5]&4:
        out[player+5]|=64
        if not out[player+5]&32:out=append(out,player,footer)
        out[footer+2]=((out[player+6]+1)&255)|128
    out[player+5]&=253;out[player]=out[footer+2]
    if not out[10]&1:out[player+1]=(out[player+1]-1)&255
    return out


def restart(ram,player=0x30):
    """1423–1450: reinstall the saved root before the logical selector."""
    checked(ram,player);out=bytearray(ram)
    raw=out[player]
    if not 128<=raw<234:raise ValueError('Unencoded restart root')
    fresh=bool(out[player+1]&64 or out[player+5]&64)
    out[player+1]&=191;out[0x12]=raw;out[14]=raw;out[15]=0 if fresh else 1
    out[8]&=254
    return out


def room_invariants(rom):
    model=cine_room_optimality.Model(rom,'dle21')
    graph,values,removed=rom_controls.simplify_controls(model,model.graph())
    rom_proof.verify(graph,values);index={s:i for i,s in enumerate(graph['states'])}
    desc=verify_dl1_scheduler.descriptors(rom,'dle21')
    playable={0}|{s for d in desc.values() for s in d['scenes']}
    mirrors=[]
    for raw in rom[0x22f4:rom.index(255,0x22f4)]:
        a=raw&127
        if a<51 and (a in playable or a+1 in playable):
            playable.update((a,a+1));mirrors.append((a,a+1))
    effects,_=verify_dl1_scheduler.room_effects(model,graph,playable)
    for scene in playable:
        if any(values[k][index[scene,0]]!=values[k][index[scene,1]] for k in values):
            raise ValueError('DLE step-one restart changes the root objective')
    for a,b in mirrors:
        for step in (0,1):
            if any(values[k][index[a,step]]!=values[k][index[b,step]] for k in values):
                raise ValueError('DLE retry mirror changes the root objective')
    pending=set();fatal_count=0;dragon=[]
    for scene,step in graph['states']:
        if scene not in playable:continue
        record=model.record(scene,step)
        if not record['death']:continue
        fatal_count+=1
        if scene==36:
            dragon.append(step)
            if not record['trailer'][4]&4:raise ValueError('Dragon death can enter the pending list')
        if (scene|128) not in EXCLUDED and not record['trailer'][4]&4:pending.add(scene)
    rows=[]
    for scene in sorted(pending):
        u=index[scene,0]
        if values['fewest'][u] is None or len(effects[u])!=1 or ('win',) in effects[u]:
            raise ValueError('Pending room lacks an ordinary surviving boundary')
        rows.append(dict(scene=scene,root_values={k:v[u] for k,v in values.items()},
                         semantic_exit=next(iter(effects[u]))))
    return dict(playable_scenes=sorted(playable),pending_rooms=rows,fatal_records=fatal_count,
                dragon_immediate_retry_death_steps=sorted(dragon),mirrors=mirrors,
                all_factory_root_zero_one_values_equal=True,all_retry_mirror_values_equal=True,
                pending_room_values_order_independent=True,
                scope='Room potentials and retry-root invariants; full life/scheduler composition is separate')


def audit(rom,build):
    kernel=rom_kernel.Kernel(rom,build)
    counts=dict(append=0,drain=0,begin=0,dispatch=0,life=0,restart=0,selector_bypass=0)
    # Original-CPU checks cover complete RAM effects and reject reads of
    # unmodeled history/progress/score state, rather than only output roots.
    def verify(ram,player,kind):
        entry=dict(append=APPEND,drain=DRAIN,begin=BEGIN,dispatch=DISPATCH,life=LIFE,restart=RESTART)[kind]
        expected=globals()[kind](ram,player)
        stop=0x1519 if kind=='life' else 0x1450 if kind=='restart' else 0xdead
        actual,regs=kernel.call(ram,entry,stop=stop,de=0xa000+player,refresh=127)
        if actual[:0x3d0]!=expected[:0x3d0] or regs['observations']:
            raise ValueError('Original pending-room primitive differs: '+kind)
        reads,writes=kernel.access()
        allowed={8,10,0x10,0x11,14,15,0x12,player,player+1,player+5,player+6,player+0x56,0x202,
                 player+0xa0,player+0xa1,0x205,*range(player+0x90,player+0x98)}
        if any(a<0x3d0 and a not in allowed for a in reads|writes):
            raise ValueError('Pending-room routine accesses undeclared state')
        counts[kind]+=1
    for player in (0x30,0x38):
        for empty in range(9):
            for raw in range(256):
                for bonus in (0,2):
                    ram=bytearray(1024);ram[player+5]=bonus|0x50;ram[0x202]=raw
                    for slot in range(8):ram[player+0x90+slot]=0x81+slot if slot<empty else 0
                    verify(ram,player,'append')
        for occupancy in range(256):
            for flags in (0,8,32,64,128,160,192,255):
                for raw in sorted(FLUSH):
                    ram=bytearray(1024);ram[8]=255;ram[player+5]=flags
                    ram[player+6]=0x89;ram[player+0xa0]=raw;ram[player+0xa1]=0x8e;ram[0x12]=raw
                    for slot in range(8):ram[player+0x90+slot]=0x81+slot if occupancy&(1<<slot) else 0
                    verify(ram,player,'drain');verify(ram,player,'begin')
        for raw in range(128,234):
            for slot in range(8):
                ram=bytearray(1024);ram[player+0x90+slot]=raw;ram[player+5]=160
                verify(ram,player,'drain')
        for outcome in range(256):
            for flags in range(256):
                ram=bytearray(1024);ram[0x12]=outcome;ram[player+5]=flags
                ram[player+6]=0x89;ram[player+0xa0]=0xa8;ram[player+0xa1]=0x8e
                ram[8]=255;ram[0x205]=255;ram[14]=0x87;ram[15]=7
                ram[player+0x90]=0x9a
                verify(ram,player,'dispatch')
        for occupancy in range(256):
            for raw in sorted(FLUSH):
                ram=bytearray(1024);ram[0x12]=raw;ram[player+6]=0x89
                for slot in range(8):ram[player+0x90+slot]=0x81+slot if occupancy&(1<<slot) else 0
                verify(ram,player,'dispatch')
        # Pending-room execution bypasses the logical selector entirely,
        # irrespective of the room's high-byte exit code. Its queue drain is
        # performed by the independently audited dispatcher above.
        for outcome in range(256):
            ram=bytearray(1024);ram[0x10]=50;ram[0x11]=216
            ram[0x12]=outcome;ram[player+5]=32
            actual,regs=kernel.call(ram,0x1cc3,de=0xa000+player)
            reads,writes=kernel.access()
            if actual[:0x3d0]!=ram[:0x3d0] or regs['observations'] or any(i<0x3d0 for i in writes):
                raise ValueError('Queued room did not bypass logical selection')
            if any(i<0x3d0 and i not in (0x10,0x12,player+5) for i in reads):
                raise ValueError('Pending selector reads undeclared state')
            counts['selector_bypass']+=1
        for raw in range(128,234):
            for flags in (0,2,8,32,34,64,128,160,255):
                for effect in (0,4,128,132):
                    ram=bytearray(1024);ram[0x10]=50;ram[0x11]=216;ram[8]=255
                    ram[player+5]=flags;ram[player+6]=0x89;ram[player+1]=131
                    ram[0x202]=raw;ram[0x205]=effect
                    ram[player+0x90]=0x81
                    verify(ram,player,'life')
        for occupancy in range(256):
            ram=bytearray(1024);ram[0x10]=50;ram[0x11]=216;ram[player+1]=3
            ram[player+6]=0x89;ram[0x202]=0x9a
            for slot in range(8):ram[player+0x90+slot]=0x81+slot if occupancy&(1<<slot) else 0
            verify(ram,player,'life')
        for raw in range(128,234):
            for lives in (0,1,3,63,64,65,128,131,192,255):
                for flags in (0,32,64,128,192,255):
                    ram=bytearray(1024);ram[player]=raw;ram[player+1]=lives;ram[player+5]=flags;ram[8]=255
                    verify(ram,player,'restart')
    return dict(native_cases=counts,total_cases=sum(counts.values()),
                queue_slots=8,players=[0x30,0x38],excluded_append_bytes=sorted(EXCLUDED),
                flush_boundaries=sorted(FLUSH),
                room_invariants=room_invariants(rom),
                invariant='Pending drain never reads or changes active descriptor history, progress or score; it installs one physical root and optionally step 1',
                limits='Exact life-loss mutation, restart prefix, queue/dispatcher and pending-selector bypass; complete life/scheduler composition and physical replay remain separate')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rom',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    started=time.monotonic();rom=rom_tables.load(a.rom,'dle21');result=audit(rom,a.output/'build')
    result.update(rom_sha256=hashlib.sha256(rom).hexdigest(),seconds=time.monotonic()-started,
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        sources={n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in
                 ('dle_retry_rules.py','rom_kernel.py','rom_kernel.c','rom_tables.py',
                  'cine_room_optimality.py','rom_controls.py','verify_dl1_scheduler.py','rom_proof.py')})
    (a.output/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':main()
