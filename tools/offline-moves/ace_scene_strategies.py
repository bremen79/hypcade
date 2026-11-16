#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Recalculate A3 local strategies with explicit replay/scene continuation cost.

Global values are only an independent cross-check. Timings remain original ROM
windows, and the exported native host policies contain only ranking metadata.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

import ace_rules
import cine_global_model
import rom_controls
import rom_proof
import rom_tables
from scene_strategies import solve_scenes, part_for

ROOT=Path(__file__).resolve().parent


def block(state):
    # Checkpoint remains inside a local block. A bounded physical replay is a
    # distinct continuation because it changes the replay flag or the scene.
    return state[0],state[1],state[3],state[4]


def generate(rom_path,output):
    output.mkdir(parents=True,exist_ok=True)
    sources={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
             ('ace_scene_strategies.py','ace_rules.py','cine_recovery_model.py','cine_global_model.py',
              'scene_strategies.py','rom_tables.py','rom_proof.py','rom_controls.py')}
    rom=rom_tables.load(rom_path,'ace')
    (output/'inventory.json').write_text(json.dumps(rom_tables.inventory(rom,'ace'),separators=(',',':'))+'\n')
    started=time.monotonic();cases=[]
    for skill in ('cadet','captain','ace'):
        model=ace_rules.Model(rom,skill)
        graph,reference,removed=rom_controls.simplify_controls(model,model.graph())
        values,paths,blocks=solve_scenes(graph,key=block)
        if values!=reference:raise ValueError('A3 local exit-cost values differ from global solution')
        (output/(skill+'-proof.json')).write_text(json.dumps(dict(
            game='ace',skill=skill,graph=graph,values=values),separators=(',',':'))+'\n')
        rankings={o:rom_proof.ranked(graph,values,o) for o in ('shortest','highest-score')}
        if any(unequal for _,unequal in rankings.values()):raise ValueError('Unresolved unequal branch values')
        with (output/(skill+'-values.jsonl')).open('w') as stream:
            stream.write(json.dumps(dict(schema=1,game='ace',skill=skill,timing='live-rom',
                cost='local scene inputs/reward + chosen exit continuation',context='episode,scene,step,cursor,replay,checkpoint,alias'))+'\n')
            for u,state in enumerate(graph['states']):
                choices={}
                for objective,(rows,_) in rankings.items():
                    choices[objective]=[]
                    for value,label,branch_values in rows[u]:
                        targets=next(ts for lab,ts in graph['actions'][u] if lab==label)
                        parts=[part_for(graph,paths,values,objective,u,label,v,key=block) for v in targets]
                        choices[objective].append(dict(label=label,value=value,targets=targets,
                                                      branches=parts,branch_values=branch_values))
                stream.write(json.dumps(dict(state=u,context=state,potential={k:v[u] for k,v in values.items()},
                                             strategies=choices),separators=(',',':'))+'\n')
        for objective in rankings:
            cine_global_model.write_ace_policy(model.base,graph,values,objective,output/(skill+'-'+objective+'.policy'))
        cases.append(dict(skill=skill,states=len(graph['states']),blocks=blocks,
                          global_value_differences=0,initial={k:v[0] for k,v in values.items()},removed_controls=len(removed)))
        print(skill,len(graph['states']),'contexts',blocks,'local blocks; all four values match',flush=True)
    if any(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h for n,h in sources.items()):
        raise ValueError('Sources changed during A3 generation')
    manifest=dict(game='ace',rom_sha256=hashlib.sha256(rom).hexdigest(),sources=sources,cases=cases,
                  timing='live-rom',seconds=time.monotonic()-started,
                  peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file() and p.name!='manifest.json'},
                  scope='Source candidate; original ROM timing, contextual local + exit costs; no APK integration')
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();generate(a.rom,a.output)


if __name__=='__main__':main()
