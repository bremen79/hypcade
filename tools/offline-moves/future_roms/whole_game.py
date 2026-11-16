#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Search complete death-free games with disk-backed full-machine checkpoints.

The local ROM policy orders/completes trials; only a completed game's final
score and total physical presses determine the whole-game incumbent. Bounded
search is not a proof of global optimality. No Android emulator is launched.
"""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import sqlite3
import subprocess
import time
from types import SimpleNamespace

import moves
import rom_tables
import score_routes
from future_roms import game_graph

ROOT = CORE


def objective_key(score, presses, objective):
    return (-score,presses) if objective=='highest-score' else (presses,-score)


def alternatives(inventory):
    """Retain unranked actions too: local reachability must not prune search."""
    records={r['address']:r for r in inventory['records']}
    result={}
    for node in inventory['nodes']:
        record=records[node['address']];options={(0,0,0)}
        for item in record['inputs']:
            if item['control'] is None:continue
            options.update((item['control'],w['window'],w['outcome'])
                           for w in item['windows'] if w['ticks'] and w['outcome']!=255)
        result[(node['scene'],node['step'])]=sorted(options)
    return result


def player_source(source):
    """Instrument the shared player, refusing ambiguous source substitutions."""
    text=source[source.index('static int play_tables('):source.index('\n#ifndef HYPCADE_ROM_ROUTES_NO_MAIN')]
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('Shared ROM player changed: '+old)
        text=text.replace(old,new)
    replace('static int play_tables(', 'static int rollout_tables(')
    replace('Machine m;snapshot_restore(&m,&g->nodes[0].snapshot,g);',
            'Machine m;snapshot_restore(&m,has_origin?&origin.snapshot:&g->nodes[0].snapshot,g);')
    replace('char checkpoint[33];state_text(checkpoint,&m,g,ROUTE_DECISION);',
            'char checkpoint[33];state_text(checkpoint,&m,g,ROUTE_DECISION);\n'
            '    if(has_origin)memcpy(checkpoint,origin.checkpoint,sizeof checkpoint);')
    replace('unsigned previous_scene=UINT_MAX,previous_step=UINT_MAX;',
            'unsigned previous_scene=UINT_MAX,previous_step=UINT_MAX,last_capture=UINT_MAX;\n'
            '    if(has_origin)checkpoint_cycle=origin.checkpoint_cycle;')
    replace('if(scene!=previous_scene || step!=previous_step) {',
            'if(forced_active && (scene!=forced_choice.scene || step!=forced_choice.step))forced_active=false;\n'
            '        bool new_record=scene!=previous_scene || step!=previous_step;\n'
            '        if(new_record) {')
    replace('bool committed=false;',
            'bool forcing=forced_active;\n'
            '        if(forcing)best=&forced_choice;\n'
            '        if(new_record || played_count!=last_capture) {\n'
            '            whole_branch(&m,g,checkpoint,checkpoint_cycle,best);last_capture=played_count;\n'
            '        }\n'
            '        bool committed=false;')
    replace('RomChoice *match=NULL;',
            'if(forcing && (slot%3!=forced_choice.window || outcome!=forced_choice.outcome))continue;\n'
            '                RomChoice *match=NULL;')
    replace('if(!match || match->rank>best->rank || match->rank>=desired_rank)continue;',
            'if(forcing)match=&forced_choice;\n'
            '                if(!match || match->rank>best->rank || match->rank>=desired_rank)continue;')
    replace('!rom_effective(&m,&trial,g,&edge,phase)',
            '(!forcing && !rom_effective(&m,&trial,g,&edge,phase))')
    replace('m=trial;connect_machine(&m);monitor_start(&live,&m);committed=true;',
            'm=trial;connect_machine(&m);monitor_start(&live,&m);committed=true;\n'
            '                if(forcing)forced_active=false;')
    # Both victory paths write the same independently replayable trace format.
    if text.count('save_trace(output,g,&m)')!=2:raise ValueError('Shared victory paths changed')
    text=text.replace('save_trace(output,g,&m)','whole_save_trace(output,g,&m)')
    text=text.replace('printf(', 'audit_printf(').replace('faudit_printf(', 'fprintf(')
    return '// Generated from rom_routes.c; original notices remain in that source.\n'+text


def identity():
    result=score_routes.source_identity()
    for name in ('whole_game.py','whole_game.c','game_graph.py','rom_routes.c','rom_tables.py'):
        path=source_path(name)
        result[str(path.relative_to(REPO))]=hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def build(folder):
    moves.verify_vendor();folder.mkdir(parents=True,exist_ok=True)
    sources=identity();binary=folder/'whole-game';stamp=folder/'sources.json'
    if binary.exists() and stamp.exists() and json.loads(stamp.read_text())==sources:return binary
    (folder/'whole_player.inc').write_text(player_source((source_path('rom_routes.c')).read_text()))
    src=ROOT/'vendor/src'
    subprocess.run([os.environ.get('CC','cc'),'-O3','-ffp-contract=off','-std=c11','-D_POSIX_C_SOURCE=200809L',
                    '-Wall','-Wextra','-Werror','-I'+str(folder),'-I'+str(ROOT),'-I'+str(src),str(source_path('whole_game.c')),
                    *[str(src/p) for p in moves.SOURCES],'-lz','-lm','-o',str(binary)],check=True)
    if identity()!=sources:raise ValueError('Sources changed during compilation')
    moves.atomic_json(stamp,sources);return binary


class Worker:
    def __init__(self,command,log):
        self.log=log.open('wb');self.buffer=bytearray()
        self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log)
        self.deadline=time.monotonic()+120
        try:
            event=self.read()
            if event['type']!='ready':raise ValueError('Worker did not boot')
            self.root=event
        except BaseException:
            self.close();raise

    def send(self,line):
        self.process.stdin.write((line+'\n').encode());self.process.stdin.flush()

    def read(self):
        while True:
            while b'\n' not in self.buffer:
                remaining=self.deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('Whole-game worker timed out')
                ready,_,_=select.select([self.process.stdout],[],[],remaining)
                if not ready:raise TimeoutError('Whole-game worker timed out')
                data=os.read(self.process.stdout.fileno(),65536)
                if not data:raise RuntimeError('Whole-game worker exited; inspect worker.log')
                self.buffer.extend(data)
            line,_,self.buffer=self.buffer.partition(b'\n')
            if line.startswith(b'{'):return json.loads(line)
            self.log.write(line+b'\n')

    def close(self):
        if self.process.poll() is None:
            try:self.send('QUIT');self.process.wait(timeout=5)
            except (BrokenPipeError,subprocess.TimeoutExpired):
                self.process.kill();self.process.wait()
        self.log.close()


def replay(verifier,args,trace,log):
    config=SimpleNamespace(rom=args.rom,game=args.game,skill=args.skill,start_delay=args.start_delay,
                           difficulty=args.difficulty,max_seconds=args.max_seconds)
    with log.open('w') as stream:
        result=subprocess.run(score_routes.command(verifier,config)+['--replay',str(trace)],
                              stdout=stream,stderr=subprocess.STDOUT,timeout=120)
    rows=[json.loads(line) for line in log.read_text().splitlines() if line.startswith('{')]
    proof=next((r for r in rows if r['type']=='replay'),{})
    if result.returncode or not proof.get('verified'):raise ValueError('Independent replay failed: '+str(log))
    return proof


def export_graph(database,root,complete):
    states={'loss':dict(terminal='loss')}
    for node,key,score,cycles in database.execute('SELECT id,key,score,cycles FROM nodes'):
        states[str(node)]=dict(canonical_sha256=hashlib.sha256(key).hexdigest(),score=score,cycles=cycles,
                              expanded=True,actions=[])
    for task,node,control,window,outcome,done,target,cost in database.execute(
            'SELECT id,node,control,window,outcome,done,target,cost FROM tasks'):
        resolved=bool(done and target is not None)
        action=dict(id='input-%d'%task,control=control,window=window,outcome=outcome,resolved=resolved,
                    presses=cost if resolved else 0,outcomes=[dict(target=target,probability='1')] if resolved else [])
        states[str(node)]['actions'].append(action)
        if not resolved:states[str(node)]['expanded']=False
    for run,node,score,cost in database.execute('SELECT run,node,score,cost FROM completions'):
        target='win-%d'%run;states[target]=dict(terminal='win',score=score)
        states[str(node)]['actions'].append(dict(id='committed-rollout-%d'%run,resolved=True,presses=cost,
                                                outcomes=[dict(target=target,probability='1')]))
    return dict(format='hypcade-whole-game-graph',schema=1,root=str(root),complete=complete,states=states,
                transitions='Deterministic full CPU/RAM/player/clock state. ROM random state is preserved, not treated as a player choice.',
                committed_rollouts='Additional valid macro-actions: commit to the recorded forced choice followed by the local policy through the ending.')


def search(args,objective,binary,verifier,inventory):
    folder=args.output/objective;folder.mkdir()
    policy=rom_tables.policies(inventory,objective);policy_path=folder/'local.policy'
    rom_tables.write_policy(policy_path,policy)
    options=alternatives(inventory)
    ranks={}
    for choice in policy['choices']:
        key=(*choice['source'],choice['control'],choice['window']%3,choice['outcome'])
        ranks[key]=min(ranks.get(key,100000),choice['rank'])
    database=sqlite3.connect(folder/'frontier.sqlite')
    database.executescript('PRAGMA cache_size=-2048; PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;'
        'CREATE TABLE nodes(id INTEGER PRIMARY KEY,key BLOB UNIQUE,offset INTEGER,score INTEGER,cycles INTEGER,moves INTEGER);'
        'CREATE TABLE tasks(id INTEGER PRIMARY KEY,node INTEGER,control INTEGER,window INTEGER,outcome INTEGER,'
        'generation INTEGER,priority INTEGER,depth INTEGER,done INTEGER DEFAULT 0,target TEXT,cost INTEGER);'
        'CREATE TABLE completions(run INTEGER,node INTEGER,score INTEGER,cost INTEGER);'
        'CREATE INDEX pending ON tasks(done,generation,priority,depth,id);')
    store=folder/'checkpoints.bin';trace=folder/'candidate.trace'
    worker=Worker([str(binary),str(args.rom),args.game,args.skill,format(args.start_delay,'.17g'),
                   str(args.difficulty),str(policy_path),str(store),str(trace),str(args.max_seconds)],folder/'worker.log')
    started=time.monotonic();nodes=0;storage=0;caps=set();runs=[];best=None;baseline=None;root_node=None

    def evaluate(command,generation,task_id=None,source_node=None):
        nonlocal nodes,storage,root_node
        first_target=None;edge_cost=None
        source_moves=database.execute('SELECT moves FROM nodes WHERE id=?',(source_node,)).fetchone()[0] if source_node else 0
        worker.deadline=time.monotonic()+args.trial_timeout
        worker.send(command)
        while True:
            event=worker.read()
            if event['type']=='result':
                if task_id is not None:
                    if first_target is not None:
                        database.execute('UPDATE tasks SET target=?,cost=? WHERE id=?',(str(first_target),edge_cost,task_id))
                    elif not event['complete'] and not event['trace_limit'] and not caps:
                        database.execute('UPDATE tasks SET target="loss",cost=0 WHERE id=?',(task_id,))
                if event['complete']:
                    if source_node is None:source_node=root_node
                    database.execute('INSERT INTO completions VALUES(?,?,?,?)',
                                     (event['run'],source_node,event['score'],event['moves']-source_moves))
                    shutil.copyfile(trace,folder/('run-%04d.trace'%event['run']))
                    if task_id is not None and first_target is None:
                        # The forced action reaches the ending before another decision.
                        target='win-%d'%event['run']
                        database.execute('UPDATE tasks SET target=?,cost=? WHERE id=?',
                                         (target,event['moves']-source_moves,task_id))
                database.commit();return event
            if event['type']!='node':raise ValueError('Unexpected worker event')
            key=bytes.fromhex(event['key']);where=(event['scene'],event['step'])
            choices=options.get(where,[])
            if not any(c[0] for c in choices):worker.send('SKIP');continue
            existing=database.execute('SELECT id FROM nodes WHERE key=?',(key,)).fetchone()
            if existing:
                if task_id is not None and first_target is None:first_target=existing[0];edge_cost=event['moves']-source_moves
                worker.send('SKIP');continue
            if args.max_nodes and nodes>=args.max_nodes:
                caps.add('node-budget');worker.send('SKIP');continue
            if args.max_store_mib and storage+event['bytes']>args.max_store_mib*1024*1024:
                caps.add('disk-budget');worker.send('SKIP');continue
            worker.send('KEEP');point=worker.read()
            if point['type']!='checkpoint':raise ValueError('Missing checkpoint')
            node=database.execute('INSERT INTO nodes(key,offset,score,cycles,moves) VALUES(?,?,?,?,?)',
                                  (key,point['offset'],event['score'],event['cycles'],event['moves'])).lastrowid
            if root_node is None:root_node=node
            if task_id is not None and first_target is None:first_target=node;edge_cost=event['moves']-source_moves
            nodes+=1;storage+=event['bytes'];preferred=event['preferred']
            for control,window,outcome in choices:
                priority=ranks.get((*where,control,window,outcome),100000)
                if not control:priority=5
                if preferred==[control,window,outcome]:priority=10000
                database.execute('INSERT INTO tasks(node,control,window,outcome,generation,priority,depth) VALUES(?,?,?,?,?,?,?)',
                                 (node,control,window,outcome,generation,priority,event['moves']))
            database.commit()

    def consider(result):
        nonlocal best
        if result['trace_limit']:caps.add('trace-depth')
        if not result['complete']:return
        if best is None or objective_key(result['score'],result['moves'],objective)<objective_key(best['score'],best['moves'],objective):
            checked=replay(verifier,args,trace,folder/('replay-%04d.log'%result['run']))
            if (checked['score'],checked['move_count'])!=(result['score'],result['moves']):raise ValueError('Replay metrics differ')
            best=dict(result,independent_replay=checked)
            shutil.copyfile(trace,folder/'best.trace')
            print('[%s] new whole-game best: score=%d presses=%d run=%d'%(objective,result['score'],result['moves'],result['run']),flush=True)

    try:
        baseline=evaluate('ROOT',0)
        if not baseline['complete']:raise ValueError('Local policy failed to complete the baseline game')
        consider(baseline);shutil.copyfile(trace,folder/'local.trace')
        baseline=dict(baseline,independent_replay=best['independent_replay'])
        runs.append(baseline)
        while True:
            if args.max_rollouts and len(runs)>=args.max_rollouts:caps.add('rollout-budget');break
            if args.wall_seconds and time.monotonic()-started>=args.wall_seconds:caps.add('wall-budget');break
            if caps & {'node-budget','disk-budget'}:break
            task=database.execute('SELECT tasks.id,nodes.id,nodes.offset,control,window,outcome,generation FROM tasks JOIN nodes ON nodes.id=tasks.node WHERE done=0 ORDER BY generation,priority,depth,tasks.id LIMIT 1').fetchone()
            if task is None:break
            task_id,source_node,offset,control,window,outcome,generation=task
            database.execute('UPDATE tasks SET done=1 WHERE id=?',(task_id,));database.commit()
            result=evaluate('RUN %d %d %d %d'%(offset,control,window,outcome),generation+1,task_id,source_node)
            result['task']=task_id;result['forced_choice']=[control,window,outcome];runs.append(result);consider(result)
            print('[%s] rollout %d: %s; nodes=%d'%(objective,len(runs),'completed' if result['complete'] else 'rejected',nodes),flush=True)
        pending=database.execute('SELECT count(*) FROM tasks WHERE done=0').fetchone()[0]
        unresolved=database.execute('SELECT count(*) FROM tasks WHERE target IS NULL').fetchone()[0]
        graph=export_graph(database,root_node,not unresolved and not caps)
        moves.atomic_json(folder/'graph.json',graph)
        solved=game_graph.solve(graph,objective)
        report=dict(objective=objective,local=baseline,whole_game=best,rollouts=runs,nodes=nodes,pending_tasks=pending,
                    checkpoint_bytes=storage,limits_reached=sorted(caps),wall_seconds=round(time.monotonic()-started,3),
                    model_optimum_proven=solved['model_optimum_proven'],global_optimum_proven=False,
                    explicit_graph_solution=solved,unresolved_graph_actions=unresolved,
                    score_gain=best['score']-baseline['score'],presses_saved=baseline['moves']-best['moves'])
        moves.atomic_json(folder/'report.json',report);return report
    finally:
        worker.close();database.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom',type=Path,required=True);parser.add_argument('--game',choices=rom_tables.LAYOUTS,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--skill',default='ace',choices=('cadet','captain','ace'))
    parser.add_argument('--difficulty',type=int,default=0);parser.add_argument('--start-delay',type=float,default=0)
    parser.add_argument('--objective',action='append',choices=('highest-score','shortest'))
    parser.add_argument('--max-rollouts',type=int,default=32);parser.add_argument('--max-nodes',type=int,default=4000)
    parser.add_argument('--max-store-mib',type=int,default=128);parser.add_argument('--wall-seconds',type=int,default=300)
    parser.add_argument('--trial-timeout',type=int,default=120);parser.add_argument('--max-seconds',type=int,default=3600)
    parser.add_argument('--build-dir',type=Path,default=REPO/'local-tools/whole-game-build')
    args=parser.parse_args();args.rom=args.rom.resolve();args.output=args.output.resolve()
    if args.output.exists():parser.error('Choose a new output directory')
    if args.skill not in rom_tables.skills(args.game):parser.error('Skill is not supported by this ROM')
    if not 0<=args.difficulty<rom_tables.difficulty_count(args.game):parser.error('Invalid difficulty')
    if not 0<=args.start_delay<=60:parser.error('Start delay must be finite and 0..60')
    if not 1<=args.max_seconds<=7200 or args.trial_timeout<1:parser.error('Invalid timeout')
    if any(getattr(args,n)<0 for n in ('max_rollouts','max_nodes','max_store_mib','wall_seconds')):parser.error('Budgets cannot be negative')
    args.output.mkdir(parents=True)
    chips=moves.identity(args.rom,args.game);inventory=rom_tables.inventory(rom_tables.load(args.rom,args.game),args.game)
    sources=identity();binary=build(args.build_dir.resolve());verifier=score_routes.build()
    report=dict(game=args.game,skill=args.skill,difficulty=args.difficulty,start_delay=args.start_delay,rom_chips=chips,
                sources=sources,backend='host-original-cpu-player',results=[],global_optimum_proven=False,
                model='Death-free, finite-horizon full-machine search. One physical 100ms single-control pulse at the first acknowledged changed-decision point for each decoded control/window/outcome, or wait through the record. Full-machine canonical bytes identify nodes; no scene-only state merges.',
                limitations=['No proof over every possible press time, simultaneous diagonal or intentional-death strategy.',
                             'The endpoint is the known victory clip followed by ten seconds of settled score.',
                             'Local policies complete trials and order alternatives; they are not pruning bounds.',
                             'A budget-limited result is the best independently replayed complete game found, not a proven global optimum.'])
    for objective in dict.fromkeys(args.objective or ('highest-score','shortest')):
        report['results'].append(search(args,objective,binary,verifier,inventory))
        if identity()!=sources:raise ValueError('Sources changed during search')
        moves.atomic_json(args.output/'report.json',report)
    print(json.dumps([dict(objective=r['objective'],local_score=r['local']['score'],whole_score=r['whole_game']['score'],
                           local_presses=r['local']['moves'],whole_presses=r['whole_game']['moves'],
                           limits=r['limits_reached'],model_optimum_proven=r['model_optimum_proven']) for r in report['results']],indent=2))


if __name__=='__main__':main()
