#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Decode revision-pinned Cinematronics ROM step tables and plan local routes.

Scene IDs include system/prototype entries and aliases; they are not a count of
unique playable rooms. Structural closure is separate from runtime coverage.
"""
import argparse
import json
from pathlib import Path
import zipfile
import zlib

LAYOUTS = {
    'sae': dict(chips=5, prefix='sae10', crc=[0xcbc5e425,0x71a26f47,0xbac5cdd8,0xe18380f9,0x8a536cb0],
                roots=0x2571, count=80, score=0x2503, multiplier=2,
                dispatch_scenes=[77,78,79]),
    'dle21': dict(chips=3, prefix='dle21', crc=[0x4f8af481,0x5fca04c5,0xc14f36b3],
                  roots=0x2370, count=106, score=0x2302, multiplier=1),
    'ace': dict(chips=5, prefix='sa_a3', crc=[0x427522d0,0x18d0262d,0x4646832d,0x57db2a79,0x85cbcdc4],
                roots=0x2183, count=33, score=0x2115, multiplier=2),
}
# US revisions A-D share table structure; E/F add four root slots.
LAYOUTS['lair_a'] = {'chips': 5, 'prefix': 'dl_a', 'crc': [3614344172, 2795971544, 1388679188, 2454524658, 1858271681], 'roots': 14626, 'count': 90, 'score': 14516, 'multiplier': 1, 'difficulties': 4, 'dips': [0, 8], 'pr7820': True}
LAYOUTS['lair_b'] = {'chips': 5, 'prefix': 'dl_b', 'crc': [3614344172, 1733365821, 1388679188, 2454524658, 1858271681], 'roots': 14626, 'count': 90, 'score': 14516, 'multiplier': 1, 'difficulties': 4, 'dips': [0, 8], 'pr7820': True}
LAYOUTS['lair_c'] = {'chips': 5, 'prefix': 'dl_c', 'crc': [3468681834, 1733365821, 1388679188, 2454524658, 1858271681], 'roots': 14626, 'count': 90, 'score': 14516, 'multiplier': 1, 'difficulties': 4, 'dips': [0, 8], 'pr7820': True}
LAYOUTS['lair_d'] = {'chips': 5, 'prefix': 'dl_d', 'crc': [190492960, 2481717243, 585521439, 1601311435, 726047881], 'roots': 14626, 'count': 90, 'score': 14516, 'multiplier': 1, 'difficulties': 4, 'dips': [0, 8], 'pr7820': False}
LAYOUTS['lair_e'] = {'chips': 4, 'prefix': 'dl_e', 'crc': [43516966, 2543668375, 2306601077, 1321204645], 'roots': 8147, 'count': 94, 'score': 8037, 'multiplier': 1, 'difficulties': 4, 'dips': [34, 216], 'pr7820': False}
LAYOUTS['lair_f'] = {'chips': 4, 'prefix': 'dl_f', 'crc': [117205313, 3703693298, 2874232411, 2820092494], 'roots': 8456, 'count': 94, 'score': 8346, 'multiplier': 1, 'difficulties': 4, 'dips': [34, 216], 'pr7820': False}

def space_ace(game):
    return game in ('ace', 'sae')

def difficulty_count(game):
    return LAYOUTS[game].get('difficulties', 4 if game=='ace' else 2 if game=='sae' else 1)

def skills(game):
    return ('cadet','captain','ace') if space_ace(game) else ('ace',)

CONTROLS = {0:16,1:1,2:2,4:4,8:8}


def load(path, game):
    spec=LAYOUTS[game]
    with zipfile.ZipFile(path) as archive:
        names={n.lower():n for n in archive.namelist()}
        parts=[archive.read(names[f'{spec["prefix"]}_u{i}.bin']) for i in range(1,spec['chips']+1)]
    if [zlib.crc32(x) for x in parts]!=spec['crc']:
        raise ValueError('Unsupported ROM revision')
    return b''.join(parts)


def word(rom, p):
    if not 0<=p<len(rom)-1:raise ValueError('Pointer outside ROM')
    return int.from_bytes(rom[p:p+2],'little')


def decode_record(rom, address, game):
    p=address;inputs=[]
    def byte():
        nonlocal p
        if p>=len(rom):raise ValueError('Truncated step record')
        result=rom[p];p+=1;return result
    for index in range(64):
        header=byte()
        if not header&128:break
        selector=byte();outcomes=[byte() for _ in range(((header&0x60)>>5)+1)]
        extra=byte() if header&16 else None
        count=selector&3;delay=byte();windows=[]
        for window in range(count):
            choice=(selector>>(2+2*window))&3
            if choice>=len(outcomes):raise ValueError('Outcome selector outside stored outcomes')
            windows.append(dict(window=window,ticks=byte(),outcome=outcomes[choice]))
        inputs.append(dict(slot=index,control=CONTROLS.get(header&15),rom_control=header&15,
                           header=header,selector=selector,outcomes=outcomes,extra=extra,
                           delay_ticks=delay,windows=windows))
    else:raise ValueError('Unterminated input list')
    trailer=[header]+[byte() for _ in range(6)]
    # Ace's optional trailer fields are decoded separately from the common
    # seven bytes. Their runtime interpretation stays with the original ROM.
    extension=[]
    if game in ('ace', 'sae'):
        if trailer[4]&32:extension.extend(byte() for _ in range(2))
        if trailer[4]&64:extension.extend(byte() for _ in range(2))
        if trailer[4]&1:extension.append(byte())
    score=word(rom,LAYOUTS[game]['score']+2*(trailer[0]&15))*LAYOUTS[game]['multiplier']
    return dict(address=address,end=p,inputs=inputs,trailer=trailer,extension=extension,
                award=score,death=bool(trailer[0]&16),scene_exit=bool(trailer[0]&32),
                system=bool(trailer[0]&64))


def inventory(rom, game):
    spec=LAYOUTS[game];groups=[];records={};nodes={}
    for scene in range(spec['count']):
        base=word(rom,spec['roots']+scene*2)
        if not base:continue
        if scene in spec.get('dispatch_scenes', []):
            # SAE's final three roots are FF-terminated scene-choice byte
            # lists, not arrays of step pointers. Preserve them for audit.
            end=rom.index(255,base)
            groups.append(dict(scene=scene,address=base,steps=[],
                               dispatch=list(rom[base:end+1])))
            continue
        boundary=len(rom);steps=[]
        for step in range(128):
            pos=base+step*2
            if pos>=boundary:break
            address=word(rom,pos)
            if not address:steps.append(dict(step=step,address=None));continue
            if not spec['roots']+2*spec['count']<=address<len(rom):break
            if address>=base:boundary=min(boundary,address)
            if pos>=boundary:break
            record=decode_record(rom,address,game);records[address]=record
            node=dict(scene=scene,step=step,address=address);nodes[(scene,step)]=node;steps.append(node)
        groups.append(dict(scene=scene,address=base,steps=steps))
    edges=[];missing=[]
    for source,node in nodes.items():
        record=records[node['address']]
        # Death/scene-exit/system records dispatch through ROM code, not this
        # timeout field. Do not invent outgoing edges from their trailer bytes.
        if record['death'] or record['scene_exit'] or record['system']:continue
        choices=[dict(control=0,window=0,outcome=record['trailer'][1])]
        choices += [dict(control=i['control'],window=3*i['slot']+w['window'],outcome=w['outcome'])
                    for i in record['inputs'] if i['control'] is not None for w in i['windows'] if w['ticks']]
        for choice in choices:
            outcome=choice['outcome']
            if outcome==255:continue
            target=(outcome&127,0) if outcome&128 else (source[0],outcome)
            edge=dict(source=list(source),target=list(target),**choice)
            if target not in nodes:missing.append(edge)
            edges.append(edge)
    return dict(game=game,layout=spec,groups=groups,records=list(records.values()),nodes=list(nodes.values()),
                edges=edges,unresolved_targets=missing,all_scenes_proven=False,
                limits='Table boundaries inferred from forward data pointers. ROM dispatch, skill, random routing and timing require natural execution validation.')


def policies(data, objective):
    nodes={(n['scene'],n['step']):n for n in data['nodes']};records={r['address']:r for r in data['records']}
    outgoing={n:[] for n in nodes}
    for edge in data['edges']:outgoing[tuple(edge['source'])].append(edge)
    memo={};cycles=set()
    def solve(key,active):
        if key in memo:return memo[key]
        if key in active:cycles.add(key);return None
        r=records[nodes[key]['address']]
        if r['death'] or r['system']:return None
        if r['scene_exit']:
            memo[key]=(0,r['award']);return memo[key]
        options=[]
        for e in outgoing[key]:
            target=tuple(e['target'])
            if target not in nodes:continue
            dest=records[nodes[target]['address']]
            if dest['death']:continue
            if e['outcome']&128:continuation=(0,0)
            else:continuation=solve(target,active|{key})
            if continuation is None:continue
            moves=continuation[0]+bool(e['control']);score=continuation[1]+r['award']
            options.append((moves,score,e))
        if not options:return None
        rank=lambda x:(x[0],-x[1],x[2]['control'],x[2]['window']) if objective=='shortest' else (-x[1],x[0],x[2]['control'],x[2]['window'])
        best=min(options,key=rank);memo[key]=best[:2];return memo[key]
    for key in nodes:solve(key,set())
    result=[]
    for key in nodes:
        options=[]
        for e in outgoing[key]:
            target=tuple(e['target'])
            if target not in nodes:continue
            r=records[nodes[target]['address']]
            if r['death'] or (r['system'] and not e['outcome']&128):continue
            continuation=(0,0) if e['outcome']&128 else memo.get(target)
            if continuation is None:continue
            moves=continuation[0]+bool(e['control']);score=continuation[1]
            options.append(dict(**e,remaining_moves=moves,remaining_score=score))
        options.sort(key=lambda e:(e['remaining_moves'],-e['remaining_score'],e['control'],e['window']) if objective=='shortest' else (-e['remaining_score'],e['remaining_moves'],e['control'],e['window']))
        for rank,e in enumerate(options):result.append(dict(**e,rank=rank))
    return dict(objective=objective,choices=result,cyclic_nodes=[list(k) for k in sorted(cycles)],
                global_optimum_proven=False,limits='Local scene-exit optimization. ROM chooses scene order at runtime; cycles and context-sensitive dispatch are not proof of global optimality.')


def write_policy(path,data):
    lines=['HYPCADE_ROM_POLICY_V1']
    for c in data['choices']:
        lines.append('%d %d %d %d %d %d'%(*c['source'],c['control'],c['window'],c['outcome'],c['rank']))
    Path(path).write_text('\n'.join(lines)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--game',choices=LAYOUTS,required=True)
    p.add_argument('--rom',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);d=inventory(load(a.rom,a.game),a.game)
    (a.output/'inventory.json').write_text(json.dumps(d,indent=2)+'\n')
    for obj in ('shortest','highest-score'):
        policy=policies(d,obj);write_policy(a.output/(obj+'.policy'),policy)
        (a.output/(obj+'.json')).write_text(json.dumps(policy,indent=2)+'\n')
    print('ROM inventory:',len(d['groups']),'scene slots;',len(d['records']),'unique steps;',len(d['edges']),'transitions;',len(d['unresolved_targets']),'unresolved targets',flush=True)

if __name__=='__main__':main()
