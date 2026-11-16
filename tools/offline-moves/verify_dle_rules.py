#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native DLE21 selector/version invariant under its supported factory banks.

The progress counter still sets a harder flag, but bank A011.7 bypasses the
harder table offset. Do not sum obsolete harder roots into the authored queue.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

import dl1_selector
import rom_kernel
import rom_tables
import verify_dl1_scheduler


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);started=time.monotonic()
    rom=rom_tables.load(a.rom,'dle21');kernel=rom_kernel.Kernel(rom,a.output/'build')
    # Start before the direct-root branch. The shared mask-dispatch entry
    # 1D50 is valid for US descriptors but incorrectly consumes a history bit
    # for DLE's flags-08 direct-room descriptors when entered unconditionally.
    entry=0x1cc3;descriptors=verify_dl1_scheduler.descriptors(rom,'dle21')
    if rom[entry:entry+9]!=bytes.fromhex('3a10a0cb5fc0c3b109'):
        raise ValueError('Unknown complete DLE selector entry')
    cases=0;rows=[];transitions=[]
    for ep,desc in descriptors.items():
        selected=set()
        # History contains only bits authored by this descriptor. Seeding
        # arbitrary cross-descriptor bits creates impossible pointer indices.
        for history in range(desc['mask']+1):
            support=set();normal=[]
            for player in (0x30,0x38):
                for hard in (0,16):
                    for retry in (0,64):
                        context=set()
                        ram=bytearray(1024);ram[0x10]=50;ram[0x11]=216;ram[player+5]=hard|retry
                        history_base=0x60 if player==0x30 else 0x90
                        ram[history_base+ep]=history;ram[0x12]=ep|128
                        for phase in range(128):
                            out,_=kernel.call(ram,entry,de=0xa000+player,refresh=phase)
                            root=out[14]&127;selected.add(root)
                            value=(root,out[history_base+ep]&desc['mask'],0)
                            if out[15]!=int(bool(retry)) or out[player+5]!=((hard|retry)&~64):
                                raise ValueError('DLE retry changes more than the entry-step override')
                            if out[player+6]!=ep:raise ValueError('DLE selector does not publish the logical episode')
                            if player==0x30 and not hard and not retry:normal.append(value)
                            context.add(value)
                            if not desc['flags']&7 and value[1]!=history:
                                raise ValueError('DLE direct-room branch consumes history')
                            support.add(value)
                            if root not in desc['scenes'] or root>=51:
                                raise ValueError('DLE bank/version invariant failed at episode %d history=%d hard=%d phase=%d root=%d'%(ep,history,hard,phase,root))
                            cases+=1
                        # Retry and player branches change fetch counts before
                        # R is read. Compare exact support over all residues,
                        # never assume equal seeds imply equal room choices.
                        if context!=set(normal):raise ValueError('DLE context changes selector support')
            transitions.append(dict(episode=ep,history=history,targets=sorted(support)))
        rows.append(dict(episode=ep,physical_roots=sorted(selected)))
    report=dict(game='dle21',entry_pc=entry,native_cases=cases,episodes=rows,transitions=transitions,
        bank_values=dict(a010=50,a011=216),
        players=[0x30,0x38],entry_steps=[0,1],direct_descriptor_history_unchanged=True,
        equal_seed_correspondence_assumed=False,
        invariant='All decoded selector histories/phases stay in authored normal roots even when progress sets the harder flag',
        rom_sha256=hashlib.sha256(rom).hexdigest(),seconds=time.monotonic()-started,
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        sources={n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in
                 ('verify_dle_rules.py','dl1_selector.py','verify_dl1_scheduler.py','rom_kernel.py','rom_kernel.c','rom_tables.py')},
        limits='Selector/version invariant; queue/retry multiset composition and delivery checks are separate')
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(cases,'original DLE selector cases; no harder root selected')


if __name__=='__main__':main()
