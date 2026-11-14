#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the production US 3.19 RAM adapter without video or a ROM.

Cases reproduce lifecycle states observed in video-less DLE21/DL2 runs.
Only the scoreboard sink is replaced: the adapter body comes from lair2.cpp.
"""
from pathlib import Path
import argparse
import importlib.util
import subprocess

REPO = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        default=REPO / 'local-tools/dl2-scoreboard-test')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location(
        'verify_dl2', REPO / 'tools/offline-moves/verify_dl2_watch.py')
    verify = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verify)
    method = verify.driver_method((REPO / 'src/game/lair2.cpp').read_text(),
                                  'void lair2::update_android_scoreboard()')
    source = r'''
#include "scoreboard_state.h"
#include <cassert>
#include <cstdio>
#include <cstring>
struct Capture {
    char score[2][7]{};
    unsigned lives[2]{}, credits[2]{}, repaints = 0;
    void update_player_score(unsigned d, unsigned v, unsigned p) {
        assert(p < 2 && d < 6 && (v <= 9 || v == 15));
        score[p][d] = v == 15 ? ' ' : '0' + v;
    }
    void update_player_lives(unsigned v, unsigned p) { lives[p] = v; }
    void update_credits(unsigned d, unsigned v) { credits[d] = v; }
    void RepaintIfNeeded() { ++repaints; }
};
struct Dl2Machine {
    unsigned char m_cpumem[1 << 20]{};
    Capture *m_android_scoreboard = nullptr;
    void update_android_scoreboard();
    void word(unsigned at, unsigned value) {
        m_cpumem[0x10000 + at] = value;
        m_cpumem[0x10001 + at] = value >> 8;
    }
};
''' + method + r'''
int main() {
    Dl2Machine machine;
    machine.update_android_scoreboard(); // Disabled/unsupported revision.
    Capture sink;
    machine.m_android_scoreboard = &sink;
    struct Case {
        const char *name;
        unsigned players, limit, current, lives1, lives2, score1, score2;
        const char *display1, *display2;
        unsigned digit1, digit2;
    };
    const Case cases[] = {
        {"boot self-test",65535,65535,65535,65535,65535,65535,65535,"      ","      ",15,15},
        {"attract",0,0,0,0,0,0,0,"      ","      ",15,15},
        {"one player starts",1,1,0,3,3,0,0,"000000","      ",3,15},
        {"one player scores",1,1,0,2,3,12340,0,"001234","      ",2,15},
        {"one player continues",1,1,0,3,3,12340,0,"001234","      ",3,15},
        {"two players start",2,2,0,3,3,0,0,"000000","000000",3,3},
        {"player one turn",2,2,0,2,3,12340,56780,"001234","005678",2,3},
        {"player two turn",2,2,1,2,2,12340,56780,"001234","005678",2,2},
        {"player one finished",2,2,1,0,2,12340,56780,"001234","005678",15,2},
        {"player two finished",2,1,0,2,0,12340,56780,"001234","005678",2,15},
        {"one continues after two eliminated",2,1,0,3,0,12340,56780,"001234","005678",3,15},
        {"match ended with stale scores",0,0,0,0,0,12340,56780,"      ","      ",15,15},
        {"new single after two",1,1,0,3,3,0,56780,"000000","      ",3,15},
        {"unrepresentable lives",2,2,0,10,65535,12340,56780,"001234","005678",15,15},
    };
    for (const auto &c : cases) {
        machine.word(0x56a6,c.players); machine.word(0x56a4,c.limit);
        machine.word(0x56aa,c.current);
        machine.word(0x56ac,c.lives1); machine.word(0x56ae,c.lives2);
        machine.word(0x56b0,c.score1); machine.word(0x56b2,c.score2);
        machine.word(0xa156,42);
        unsigned repaints = sink.repaints;
        machine.update_android_scoreboard();
        assert(!strcmp(sink.score[0],c.display1));
        assert(!strcmp(sink.score[1],c.display2));
        assert(sink.lives[0] == c.digit1 && sink.lives[1] == c.digit2);
        assert(sink.credits[0] == 4 && sink.credits[1] == 2);
        assert(sink.repaints == repaints + 1);
        printf("PASS %s\n",c.name);
    }
}
'''
    cpp = args.output / 'scoreboard.cpp'
    cpp.write_text(source)
    binary = args.output / 'scoreboard-test'
    subprocess.run(['c++', '-std=c++17', '-O2', '-Wall', '-Wextra',
                    '-I'+str(REPO / 'src/scoreboard'),
                    str(cpp), '-o', str(binary)], check=True)
    subprocess.run([str(binary.resolve())], check=True)


if __name__ == '__main__':
    main()
