#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the production European/Italian RAM adapter, optionally with real ROMs.

The ROM run uses the original driver/VP932 methods and video-less CPU harness.
No Android runtime is started. ROMs and generated files stay outside Git.
"""
import argparse
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools/offline-moves'))
import euro_moves
import euro_tables
from verify_dl2_watch import driver_method

CAPTURE = r'''
#include "scoreboard_state.h"
#include <cassert>
#include <cstdio>
#include <cstring>
struct Capture {
    char score[2][7]{};
    unsigned lives[2]{}, credits[2]{};
    void update_player_score(unsigned d,unsigned v,unsigned p) {
        assert(p<2 && d<6 && (v<=9 || v==15));
        score[p][d]=v==15?' ':'0'+v;
    }
    void update_player_lives(unsigned v,unsigned p){lives[p]=v;}
    void update_credits(unsigned d,unsigned v){credits[d]=v;}
    void RepaintIfNeeded(){}
};
'''

UNIT = r'''
int main() {
    EuroMachine machine; Capture sink;
    machine.update_android_scoreboard(); // Disabled.
    machine.m_android_scoreboard=&sink;
    auto &m=machine.m_cpumem;
    m[0xa142]=0x12;m[0xa143]=0x34;m[0xa144]=0x56;
    m[0xa145]=0x65;m[0xa146]=0x43;m[0xa147]=0x21;
    m[0xa149]=3;m[0xa14a]=2;m[0xa14b]=0x42;
    m[0xa153]=0; machine.update_android_scoreboard();
    assert(!strcmp(sink.score[0],"123456") && !strcmp(sink.score[1],"      "));
    assert(sink.lives[0]==3 && sink.lives[1]==15);
    assert(sink.credits[0]==4 && sink.credits[1]==2);
    m[0xa153]=1;
    for(unsigned player=0;player<2;player++) {
        m[0xa152]=player; machine.update_android_scoreboard();
        assert(!strcmp(sink.score[0],"123456") && !strcmp(sink.score[1],"654321"));
        assert(sink.lives[0]==3 && sink.lives[1]==2);
    }
    m[0xa149]=0;machine.update_android_scoreboard();
    assert(sink.lives[0]==15 && !strcmp(sink.score[0],"123456"));
    m[0xa001]=1;machine.update_android_scoreboard();
    assert(!strcmp(sink.score[0],"      ") && !strcmp(sink.score[1],"      "));
    assert(sink.lives[0]==15 && sink.lives[1]==15);
    m[0xa001]=0;m[0xa142]=0xfa;m[0xa14a]=10;m[0xa14b]=0xff;
    machine.update_android_scoreboard();
    assert(!strcmp(sink.score[0],"      ") && !strcmp(sink.score[1],"654321"));
    assert(sink.lives[1]==15 && sink.credits[0]==15 && sink.credits[1]==15);
    m[0xa153]=255;machine.update_android_scoreboard();
    assert(!strcmp(sink.score[1],"      "));
    puts("PASS European/Italian BCD, player turns, eliminated players, game over and invalid values");
}
'''

ROM_MAIN = r'''
int main(int argc,char**argv) {
    assert(argc==5);unsigned players=atoi(argv[2]);bool italian=atoi(argv[3]);
    FILE*f=fopen(argv[1],"rb");assert(f && fread(machine.m_cpumem,1,32768,f)==32768);fclose(f);
    machine.m_banks[2]=italian?0xdf:0x16;machine.m_banks[3]=italian?0xef:0xf6;
    struct Input{uint64_t cycle;unsigned action,down;};vector<Input> trace;size_t at=0;
    if(strcmp(argv[4],"-")) {
        f=fopen(argv[4],"r");assert(f);unsigned long long cycle;unsigned action,down;
        while(fscanf(f,"%llu %u %u",&cycle,&action,&down)==3)trace.push_back({cycle,action,down});
        fclose(f);assert(!trace.empty());
    }
    Capture sink;machine.m_android_scoreboard=&sink;
    for(unsigned c=0;c<4;c++)irq_next[c]=1e30;
    ctc_init(1000.0/3579545,0,0,2000.0/3579545,0);
    Z80Bus bus{&machine,mem_read,mem_write,port_read,port_write};z80_init(&machine.z80,bus);
    uint64_t next_nmi=0;bool coin=false,start=false,started=false,ended=false;
    unsigned turns=0,maxscore=0,peakcredits=0;string previous;
    while(now_cycles<900ULL*3579545) {
        unsigned ms=now_cycles*1000/3579545;
        if(!trace.empty()) {
            while(at<trace.size() && now_cycles>=trace[at].cycle) {
                const auto &in=trace[at++];
                if(in.down)machine.input_enable(in.action,0);else machine.input_disable(in.action,0);
            }
        } else {
            bool newcoin=ms>=60000 && ms<64000 && ms%1000<100;
            bool newstart=ms>=65000 && ms<65200;
            if(newcoin!=coin){coin=newcoin;if(coin)machine.input_enable(SWITCH_COIN1,0);else machine.input_disable(SWITCH_COIN1,0);}
            if(newstart!=start){start=newstart;unsigned sw=players==2?SWITCH_START2:SWITCH_START1;if(start)machine.input_enable(sw,0);else machine.input_disable(sw,0);}
        }
        for(unsigned c=0;c<4;c++)if(now_cycles>=irq_next[c]){irq_next[c]+=irq_period[c];machine.do_irq(c);}
        if(now_cycles>=next_nmi) {
            next_nmi+=3579545/50;machine.do_nmi();machine.update_android_scoreboard();
            if(ms>55000) {
                unsigned credits=sink.credits[0]*10+sink.credits[1];if(credits<=99)peakcredits=max(peakcredits,credits);
                bool active=!(machine.m_cpumem[0xa001]&1);
                if(ms>65000 && active && sink.lives[0]>0 && sink.lives[0]<=9) {
                    started=true;assert(machine.m_cpumem[0xa153]+1==players);
                    turns|=1u<<machine.m_cpumem[0xa152];
                    assert((players==2) == (strcmp(sink.score[1],"      ")!=0));
                    unsigned score=atoi(sink.score[0]);maxscore=max(maxscore,score);
                }
                if(started && !active){ended=true;assert(!strcmp(sink.score[0],"      ") && !strcmp(sink.score[1],"      "));}
                char line[256];snprintf(line,sizeof line,"active=%u players=%u current=%u scores=%s/%s lives=%u/%u credits=%u",
                    active,machine.m_cpumem[0xa153]+1,machine.m_cpumem[0xa152],sink.score[0],sink.score[1],sink.lives[0],sink.lives[1],credits);
                if(previous!=line){printf("%u %s\n",ms,line);previous=line;}
                if((trace.empty() && ended) || (!trace.empty() && at==trace.size() && ms>trace.back().cycle*1000/3579545+5000))break;
            }
        }
        now_cycles+=z80_step(&machine.z80);
        if(machine.z80.irq_taken){machine.z80.irq=false;machine.z80.irq_taken=false;}
    }
    assert(started && peakcredits>0 && (turns&1));
    if(players==2)assert(turns==3);
    if(trace.empty())assert(ended);else assert(maxscore>50000);
    printf("PASS ROM players=%u turns=%u game_over=%u max_score=%u peak_credits=%u\n",players,turns,ended,maxscore,peakcredits);
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=REPO/'local-tools/euro-scoreboard-test')
    parser.add_argument('--roms', type=Path)
    parser.add_argument('--traces', type=Path, help='Optional previous verified-difficulties directory')
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    method = driver_method((REPO/'src/game/laireuro.cpp').read_text(),
                           'void laireuro::update_android_scoreboard()').replace('laireuro::', 'EuroMachine::')
    source = CAPTURE + '''
struct EuroMachine {
    unsigned char m_cpumem[65536]{};
    Capture *m_android_scoreboard=nullptr;
    void update_android_scoreboard();
};
''' + method + UNIT
    cpp = args.output/'adapter.cpp'; cpp.write_text(source)
    binary = args.output/'adapter-test'
    subprocess.run(['c++','-std=c++17','-O2','-Wall','-Wextra','-I'+str(REPO/'src/scoreboard'),str(cpp),'-o',str(binary)],check=True)
    subprocess.run([str(binary.resolve())],check=True)
    if not args.roms: return
    build = REPO/'local-tools/euro-moves-build'; euro_moves.build(build)
    prefix=(REPO/'tools/offline-moves/euro_routes.cpp').read_text().split('struct Input {')[0]
    prefix=prefix.replace('struct EuroMachine {',CAPTURE+'\nstruct EuroMachine {\n Capture *m_android_scoreboard=nullptr;void update_android_scoreboard();')
    cpp=args.output/'rom-scoreboard.cpp';cpp.write_text(prefix+method+ROM_MAIN)
    binary=args.output/'rom-scoreboard'
    subprocess.run(['c++','-std=c++17','-O3','-I'+str(build),'-I'+str(REPO/'src/scoreboard'),
                    '-I'+str(REPO/'android/app/jni'),'-I'+str(REPO/'tools/offline-moves/vendor/src'),
                    str(cpp),str(build/'z80.o'),str(build/'ldp.o'),'-o',str(binary)],check=True)
    for game in ('laireuro','lair_ita'):
        rom=args.output/(game+'.bin');rom.write_bytes(euro_tables.load(args.roms/(game+'.zip'),game))
        scenarios=[('one-player',1,'-'),('two-player',2,'-')]
        if args.traces:
            level=0 if game=='lair_ita' else 3
            scenarios.append(('winning-replay',1,str((args.traces/(game+'-'+str(level))/'highest-score-0-phase8.trace').resolve())))
        for label,players,trace in scenarios:
            log=args.output/(game+'-'+label+'.log')
            with log.open('w') as out:
                subprocess.run([str(binary.resolve()),str(rom.resolve()),str(players),str(int(game=='lair_ita')),trace],stdout=out,stderr=subprocess.STDOUT,check=True)
            print(game,label,log.read_text().splitlines()[-1],flush=True)


if __name__ == '__main__':
    main()
