#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Original complete US group-selector transducer, including bank/hard gates.

Keep correlated refresh reads inside the descriptor loader and injector. The
raw-bank shortcut and harder-flag path have different instruction counts and
cannot be substituted merely because both enable the same logical gate.
"""
import rom_tables


def entry_pc(rom):
    at=rom.find(bytes.fromhex('3a54a0856f2255a0'))
    if at<15 or rom[at-15:at-12]!=bytes.fromhex('d93e30'):
        raise ValueError('Unknown complete US group selector')
    return at-15


def descriptor_base(rom):
    at=rom.find(bytes.fromhex('3a54a0cb27cb27'))
    if at<3 or rom[at-3]!=0x21:raise ValueError('Unknown descriptor base')
    return rom_tables.word(rom,at-2)


def memory(rom,game,group,mask,used,raw_hard,hard):
    ram=bytearray(1024)
    ram[0x10]=(2 if game in ('lair_e','lair_f') else 0)|(4 if raw_hard else 0)
    ram[0x11]=8
    ram[0x35]=16 if hard else 0
    ram[0x60+group]=mask
    for i in range(5):ram[0x70+i]=128 if used&(1<<i) else 0
    at=descriptor_base(rom)+4*group
    ram[0x50:0x54]=rom[at:at+4]
    ram[0x54]=group
    return ram


def decode(rom,game,group,mask,used,out,raw_hard,hard):
    at=descriptor_base(rom)+4*group
    pointer=rom_tables.word(rom,at)
    offset=42 if game in ('lair_e','lair_f') else 40
    roots=[(v&127)+(offset if raw_hard or hard else 0) for v in rom[pointer:pointer+3]]
    root=out[14]&127
    next_mask=out[0x60+group]&7
    next_used=sum(bool(out[0x70+i])<<i for i in range(5)) if game not in ('lair_e','lair_f') else 0
    if next_used!=used:
        changed=next_used^used
        if changed&(changed-1) or used&changed or next_mask!=mask:
            raise ValueError('Optional-room resource is not monotone')
        choice=3+changed.bit_length()-1
        if root!=80+choice-3:raise ValueError('Wrong optional physical room')
    else:
        changed=next_mask^mask
        if changed==0 or changed&(changed-1) or mask&changed:
            raise ValueError('Regular room did not consume one fresh variant')
        choice=changed.bit_length()-1
        if root!=roots[choice]:raise ValueError('Wrong normal/harder physical room')
    if out[15]!=0:raise ValueError('Unexpected retry entry')
    return choice,next_mask,next_used


def extract(rom,game,kernel,raw_hard,hard,*,all_groups=True):
    table={};cases=0
    used_values=range(32) if game not in ('lair_e','lair_f') else (0,)
    pc=entry_pc(rom)
    for used in used_values:
        for mask in range(7):
            phases=[]
            ram=memory(rom,game,1,mask,used,raw_hard,hard)
            for seed in range(128):
                out,_=kernel.call(ram,pc,refresh=seed)
                value=decode(rom,game,1,mask,used,out,raw_hard,hard)
                if seed<8:phases.append(value)
                elif value!=phases[seed&7]:raise ValueError('Complete selector requires more than three phase bits')
                cases+=1
            if all_groups:
                for group in range(2,13):
                    ram=memory(rom,game,group,mask,used,raw_hard,hard)
                    for seed in range(8):
                        out,_=kernel.call(ram,pc,refresh=seed)
                        if decode(rom,game,group,mask,used,out,raw_hard,hard)!=phases[seed]:
                            raise ValueError('Logical group changes selector support beyond its masks')
                        cases+=1
            table[used,mask]=sorted({v:seed for seed,v in enumerate(phases)}.items())
    return table,dict(cases=cases,entry_pc=pc,raw_hard=raw_hard,hard=hard,
                      all_groups_checked=all_groups,phase_bits=3,
                      first_visit_extra_possible=any(c>=3 for used in used_values for (c,_,_),_ in table[used,0]))
