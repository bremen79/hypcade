#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reconstruct whole-game scheduler contracts using the original ROM CPU.

Bounded routine calls replace room-permutation or elapsed-clock enumeration.
This is a structural proof check; physical attainment and delivery are checked
by optimality.py and the independent Watch replayer respectively.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import time

import dl1_selector
import dle_scheduler_graph
import late_progression_rules
import rom_kernel
import rom_tables
import us_progression_rules
import verify_dl1_scheduler
import ace_rules
import verify_cine_recovery

ROOT=Path(__file__).resolve().parent
INPUTS=ROOT/'proof-inputs'


def audit_us(roms, output):
    saved=json.loads((INPUTS/'us-selectors.json').read_text())
    results=[]
    for case in saved['cases']:
        game=case['game'];rom=rom_tables.load(roms/(game+'.zip'),game)
        if hashlib.sha256(rom).hexdigest()!=case['rom_sha256']:
            raise ValueError('Selector proof belongs to a different ROM: '+game)
        descriptors=verify_dl1_scheduler.descriptors(rom,game)
        if json.loads(json.dumps(descriptors))!=case['descriptors']:
            raise ValueError('Changed ROM group descriptors: '+game)
        build=output/'build'/game;kernel=rom_kernel.Kernel(rom,build)
        selectors=[]
        for table in case['selector_tables']:
            expected={(r['used'],r['mask']):[(tuple(v),seed) for v,seed in r['support']]
                      for r in table['rows']}
            actual,report=dl1_selector.extract(rom,game,kernel,table['raw_hard'],table['hard'])
            if actual!=expected:
                raise ValueError('Native selector differs from saved complete support: '+game)
            selectors.append(report)
        row=dict(game=game,rom_sha256=case['rom_sha256'],selectors=selectors,
            progression=verify_dl1_scheduler.progress_audit(kernel,game,rom),
            rewards=verify_dl1_scheduler.reward_audit(kernel,game,rom))
        row['itinerary']=(late_progression_rules.audit(rom,game,build)
            if game in ('lair_e','lair_f') else us_progression_rules.audit(rom,game,case,build))
        results.append(row)
        (output/'us.json').write_text(json.dumps(dict(cases=results),indent=2)+'\n')
        print(game,'complete selector support, difficulty progression, fixed rewards and itinerary passed',flush=True)
    return results


def audit_dle(roms,output):
    folder=output/'dle';rom_path=roms/'dle21.zip'
    subprocess.run([sys.executable,str(ROOT/'verify_dle_rules.py'),'--rom',str(rom_path),
                    '--output',str(folder)],check=True)
    native=json.loads((folder/'report.json').read_text())
    actual=dle_scheduler_graph.compose(rom_tables.load(rom_path,'dle21'),native)
    dle_scheduler_graph.verify(actual)
    expected=json.loads((INPUTS/'dle-scheduler.json').read_text())
    # Ignore old execution times/source fingerprints; compare every semantic
    # state, branch, reward, rank and Bellman value to a fresh reconstruction.
    if any(json.loads(json.dumps(value))!=expected[key] for key,value in actual.items()):
        raise ValueError('Native DLE scheduler reconstruction differs from saved certificate')
    (folder/'macro.json').write_text(json.dumps(actual,separators=(',',':'))+'\n')
    print('dle21',len(actual['states']),'macro states reconstructed from original selector',flush=True)
    return dict(native_cases=native['native_cases'],macro_states=len(actual['states']),initial=actual['initial'])


def audit_space_ace(roms,output):
    rom=rom_tables.load(roms/'ace.zip','ace');kernel=rom_kernel.Kernel(rom,output/'build/ace')
    rewards=ace_rules.audit_rewards_and_progress(rom,kernel)
    rows=[]
    for skill in ('cadet','captain','ace'):
        model=ace_rules.Model(rom,skill);graph=model.graph()
        rows.append(dict(skill=skill,states=len(graph['states']),
            transition_restart_cases=verify_cine_recovery.audit(model,kernel,graph)))
    ace=dict(rom_sha256=hashlib.sha256(rom).hexdigest(),rewards_progress=rewards,cases=rows)
    subprocess.run([sys.executable,str(ROOT/'verify_sae_rules.py'),'--rom',str(roms/'sae.zip'),
                    '--output',str(output/'sae')],check=True)
    sae=json.loads((output/'sae/report.json').read_text())
    print('A3 and SAE rewards, progress and boundary rules passed on original CPU',flush=True)
    return dict(ace=ace,sae=sae)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--roms',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--board',choices=('classic','space-ace','european'),action='append',
                   help='Limit routine audits to selected boards; default is all three')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);started=time.monotonic()
    boards=set(a.board or ('classic','space-ace','european'))
    us=audit_us(a.roms,a.output) if 'classic' in boards else []
    dle=audit_dle(a.roms,a.output) if 'classic' in boards else None
    space_ace=audit_space_ace(a.roms,a.output) if 'space-ace' in boards else None
    euro=None
    if 'european' in boards:
        subprocess.run([sys.executable,str(ROOT/'verify_euro_scheduler.py'),'--roms',str(a.roms),
                        '--output',str(a.output/'european')],check=True)
        euro=json.loads((a.output/'european/report.json').read_text())
    source_names=('audit_schedulers.py','dl1_selector.py','dle_scheduler_graph.py',
        'late_progression_rules.py','us_progression_rules.py','verify_dl1_scheduler.py',
        'rom_kernel.py','rom_kernel.c','rom_tables.py','rom_proof.py',
        'cine_room_optimality.py','late_retry_rules.py','verify_dle_rules.py',
        'dle_retry_rules.py','rom_controls.py','ace_rules.py','verify_cine_recovery.py',
        'cine_recovery_model.py','cine_global_model.py','sae_rules.py','verify_sae_rules.py','rom_rules.py')
    report=dict(all_passed=True,boards=sorted(boards),us=us,dle=dle,space_ace=space_ace,european=euro,
        seconds=time.monotonic()-started,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        sources={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in source_names},
        scope='Original CPU scheduler support, reward and progression contracts for the requested boards. No Android runtime or universal phase-controllability claim.')
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
