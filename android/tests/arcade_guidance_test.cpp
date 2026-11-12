#include "arcade_guidance.h"
#include "arcade_signature.h"
#include <vector>
#include <algorithm>
#include <cassert>
#include <cstdio>
int main() {
    arcade_configure_guidance(0, false, true);
    assert(arcade_guidance_enabled() && arcade_watch_mode_enabled() && !arcade_visual_moves_enabled());
    assert(arcade_hide_dl2_move_text("lair2",32,47,2));
    assert(!arcade_hide_dl2_move_text("lair2",32,47,1));
    assert(!arcade_hide_dl2_move_text("lair2",0,47,2));
    assert(!arcade_hide_dl2_move_text("dle21",32,47,2));
    arcade_configure_guidance(2, false, true);
    assert(arcade_visual_moves_enabled() && !arcade_hide_dl2_move_text("lair2",32,47,2));
    arcade_configure_guidance(0, false, false);
    assert(!arcade_guidance_enabled() && !arcade_watch_mode_enabled());

    const ArcadeScoreMove score_moves[] = {
        {0x1234, 100, 10, 3, 1},
        {0x1234, 100, 10, 3, 4},
        {0x1234, 150, 10, 7, 1},
    };
    assert(arcade_score_move_matches(score_moves, 3, 0x1234, 3, 1, 100));
    assert(arcade_score_move_matches(score_moves, 3, 0x1234, 3, 4, 100));
    assert(!arcade_score_move_matches(score_moves, 3, 0x1234, 3, 2, 100));
    assert(!arcade_score_move_matches(score_moves, 3, 0x1234, 7, 4, 150));
    assert(!arcade_score_move_matches(score_moves, 3, 0x9999, 3, 1, 100));
    std::vector<uint8_t> memory(0x100000, 0);
    arcade_configure_dl2_moves(memory.data(), memory.size(), true);
    assert(memory[0xf2804] == 0x90 && memory[0xf2805] == 0x90);
    arcade_configure_dl2_moves(memory.data(), memory.size(), false);
    assert(memory[0xf2804] == 0xeb && memory[0xf2805] == 0x4a);
    arcade_configure_dl2_moves(memory.data(), 1, true);
    assert(memory[0xf2804] == 0xeb && memory[0xf2805] == 0x4a);
    auto word = [&](unsigned at, unsigned value) { memory[0x10000+at]=value & 255; memory[0x10000+at+1]=value>>8; };
    assert(!arcade_decode_dl2(memory.data(), memory.size()).controls);
    assert(!arcade_decode_dl2(memory.data(), 1).controls);
    word(0x56aa, 2); word(0x5698, 3);
    auto rec = memory.data() + 0x10000 + 0x5a24 + 14*3;
    rec[0]=0; rec[1]=3; rec[2]=100;
    word(0xa15c, 120); word(0xa15a, 140); word(0xa158, 119);
    auto next = arcade_decode_dl2(memory.data(), memory.size());
    assert(next.controls==8 && !next.ready);
    word(0xa158,107); assert(!arcade_decode_dl2(memory.data(),memory.size()).controls);
    word(0xa158,108); assert(arcade_decode_dl2(memory.data(),memory.size()).controls == 8);
    word(0xa158,120); auto open=arcade_decode_dl2(memory.data(),memory.size());
    assert(open.controls==8 && open.ready && open.window==next.window);
    for (auto pair : std::vector<std::pair<unsigned,unsigned>>{{1,1},{3,8},{5,2},{7,4},{10,16}}) {
        rec[1]=pair.first;
        assert(arcade_decode_dl2(memory.data(),memory.size()).controls == pair.second);
    }
    rec[1]=3;
    word(0xa158,141); assert(!arcade_decode_dl2(memory.data(),memory.size()).controls);
    word(0xa158,130); rec[0]=2; assert(!arcade_decode_dl2(memory.data(),memory.size()).controls);
    rec[0]=0; word(0x5698,65535); assert(!arcade_decode_dl2(memory.data(),memory.size()).controls);
    assert(!arcade_decode_cine(memory.data(),memory.size(),true,0).controls);
    memory[0xa0e0]=0x81; memory[0xa0e1]=1; memory[0xa0ed]=10;
    assert(!arcade_decode_cine(memory.data(),memory.size(),true,0).controls);
    assert(!arcade_decode_cine(memory.data(),10,false,0).controls);
    // Construct a move-list signature absent from the score-verified table.
    // The decoder must refuse to show a move for an unknown state.
    std::fill(memory.begin(),memory.end(),0);
    uint8_t *table=memory.data()+0xa0e0;
    for (unsigned e=0;e<3;e++) {
        uint8_t *x=table+e*16;
        x[0]=e==0?0x91:e==1?0x84:0x88;
        x[1]=1; x[2]=e==0?3:13; x[13]=67;
    }
    assert(!arcade_decode_cine(memory.data(),memory.size(),false,1571).controls);
    uint64_t identity=arcade_cine_signature(table,256);
    // Death/retry reuses slots without clearing unreferenced outcomes/scratch.
    for (unsigned seed=1;seed<256;seed++) {
        for (unsigned e=0;e<3;e++) {
            uint8_t *x=table+e*16;
            x[1]=1 | ((seed & 15)<<4); // selectors beyond the one live window
            for (unsigned k=3;k<12;k++) x[k]=uint8_t(seed*(k+e+1));
        }
        assert(arcade_cine_signature(table,256)==identity);
        auto retry=arcade_decode_cine(memory.data(),memory.size(),false,1570);
        assert(!retry.controls);
    }
    table[12]=12;
    assert(!arcade_decode_cine(memory.data(),memory.size(),false,1565).controls);
    table[12]=13;
    assert(!arcade_decode_cine(memory.data(),memory.size(),false,1565).controls);
    table[12]=0;
    table[2]=99; // changing a referenced outcome MUST change identity
    assert(arcade_cine_signature(table,256)!=identity);
    assert(!arcade_decode_cine(memory.data(),memory.size(),false,1571).controls);
    table[1]=5; table[3]=3; // selector now refers to slot 1, same semantic outcome
    assert(arcade_cine_signature(table,256)==identity);
    assert(!arcade_decode_cine(memory.data(),memory.size(),false,1571).controls);
    assert(!arcade_decode_cine(memory.data(),memory.size(),false,30000).controls);
    puts("Guidance: control-specific score matches, window boundaries, bounds, retry signatures and unknown-state refusal passed");
}
