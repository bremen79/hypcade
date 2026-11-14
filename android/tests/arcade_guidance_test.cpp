/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
#include "arcade_guidance.h"
#include "arcade_signature.h"
#include "arcade_move_policy.h"
#include "arcade_euro_policy.h"
#include <vector>
#include <algorithm>
#include <cassert>
#include <cstdio>
int main() {
    {
        std::vector<uint8_t> memory(65536);
        auto word=[&](unsigned at,unsigned value){memory[at]=value&255;memory[at+1]=value>>8;};
        word(0xa17a,648);word(0xa10f,27743);
        word(0x2088+647*32,27743);memory[0x2088+647*32+3]=14;
        memory[0xa112]=14;memory[0xa189]=14;word(0xa115+14,649);
        assert(arcade_has_calculated_moves("laireuro") && arcade_has_calculated_moves("lair_ita"));
        for(int mode : {1,2}) {
            arcade_set_move_policy(mode);
            auto move=arcade_decode_euro(memory.data(),memory.size(),"laireuro",27743);
            assert(move.ready && move.controls==1);
            assert(!arcade_decode_euro(memory.data(),memory.size(),"lair_ita",27743).controls);
        }
        assert(!arcade_decode_euro(memory.data(),memory.size(),"unknown",27743).controls);
        memory.assign(65536,0);
        word(0xa17a,60);word(0xa10f,4023);word(0x2088+59*32,4023);
        memory[0x2088+59*32+3]=200;memory[0xa112]=175;word(0xa115+10,61);
        assert(arcade_decode_euro(memory.data(),memory.size(),"laireuro",4023).ready);
        assert(!arcade_decode_euro(memory.data(),memory.size(),"lair_ita",4023).ready);
    }
    {
        // Italian record targets exceed one byte, and bit 15 must survive.
        std::vector<uint8_t> memory(65536);
        const ArcadeEuroRule rules[]={{6,0x8007,4},{6,8,8}};
        const uint16_t order[]={0,1};
        memory[0xa17a]=6;memory[0x2088+5*32]=100;memory[0x2088+5*32+3]=20;
        memory[0xa10f]=100;memory[0xa112]=15;memory[0xa189]=10;
        memory[0xa115+10]=7;memory[0xa116+10]=128;
        memory[0xa115+8]=8;
        auto pick=[&](){return arcade_select_euro_move(rules,order,2,memory.data(),memory.size(),100,true);};
        assert(pick().ready && pick().controls==4);
        memory[0xa189]=16;assert(!pick().ready);
        memory[0xa152]=1;memory[0xa289]=14;assert(pick().ready); // P2 cutoff
        memory[0xa111]=16;assert(!pick().controls); // death
        memory[0xa111]=0;memory[0xa10f]=99;assert(!pick().controls); // partial load
        memory[0xa10f]=100;memory[0xa115+10]=8;assert(pick().controls==8);
        assert(!arcade_select_euro_move(rules,order,2,memory.data(),1,100,true).controls);
        const ArcadeEuroRule wait[]={{6,0,0},{6,0x8007,4}};
        assert(!arcade_select_euro_move(wait,order,2,memory.data(),memory.size(),100,true).controls);
        memory[0xa115+10]=7;memory[0x2088+5*32+3]=200;
        memory[0xa112]=175;memory[0xa18f]=0;memory[0xa189]=0;memory[0xa152]=0;
        assert(arcade_select_euro_move(rules,order,2,memory.data(),memory.size(),100,false).ready);
        assert(!pick().ready); // Italian retains signed CP/RET M at level zero.
        memory[0xa112]=100;memory[0xa18f]=1;memory[0xa189]=90;
        memory[0xa152]=1;memory[0xa289]=110;
        assert(arcade_select_euro_move(rules,order,2,memory.data(),memory.size(),100,false).ready);
        assert(!pick().ready); // Euro uses the global cutoff; Italian uses P2.
    }
    assert(arcade_has_calculated_moves("sae") && arcade_has_calculated_moves("ace"));
    assert(!arcade_has_calculated_moves("unknown") && !arcade_has_calculated_moves(nullptr));
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

    std::vector<uint8_t> memory(0x100000, 0);
    arcade_configure_dl2_moves(memory.data(), memory.size(), true);
    assert(memory[0xf27f9] == 0x90 && memory[0xf27fa] == 0x90);
    assert(memory[0xf2804] == 0x90 && memory[0xf2805] == 0x90);
    arcade_configure_dl2_moves(memory.data(), memory.size(), false);
    assert(memory[0xf27f9] == 0x7d && memory[0xf27fa] == 0x55);
    assert(memory[0xf2804] == 0xeb && memory[0xf2805] == 0x4a);
    arcade_configure_dl2_moves(memory.data(), 1, true);
    assert(memory[0xf2804] == 0xeb && memory[0xf2805] == 0x4a);
    auto word = [&](unsigned at, unsigned value) { memory[0x10000+at]=value & 255; memory[0x10000+at+1]=value>>8; };
    assert(!arcade_decode_dl2(memory.data(), memory.size()).controls);
    assert(!arcade_decode_dl2(memory.data(), 1).controls);
    word(0x56aa, 2); word(0x5698, 3);
    auto rec = memory.data() + 0x10000 + 0x5a24 + 14*3;
    rec[0]=0; rec[1]=3; rec[2]=100;
    word(0xa160, 120); word(0xa15c, 135); word(0xa15a, 140); word(0xa158, 119);
    auto next = arcade_decode_dl2(memory.data(), memory.size());
    assert(next.controls==8 && !next.ready);
    word(0xa158,107); assert(!arcade_decode_dl2(memory.data(),memory.size()).controls);
    word(0xa158,108); assert(arcade_decode_dl2(memory.data(),memory.size()).controls == 8);
    word(0xa158,120); auto open=arcade_decode_dl2(memory.data(),memory.size());
    assert(open.controls==8 && open.ready && open.window==next.window);
    // A15C is a later cue threshold; acceptance already opens at A160.
    word(0xa15c,139);
    assert(arcade_decode_dl2(memory.data(),memory.size()).ready);
    for (unsigned type : {0U,1U,4U,5U}) {
        rec[0]=type;
        assert(arcade_decode_dl2(memory.data(),memory.size()).ready);
    }
    rec[0]=0;
    for (auto pair : std::vector<std::pair<unsigned,unsigned>>{{1,1},{3,8},{5,2},{7,4},{10,16}}) {
        rec[1]=pair.first;
        assert(arcade_decode_dl2(memory.data(),memory.size()).controls == pair.second);
    }
    rec[1]=3;
    word(0xa158,140); assert(!arcade_decode_dl2(memory.data(),memory.size()).controls);
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
    // Complete-rule lookup works without any sampled timing rows, including
    // a retry-only state and a conditionally compacted runtime input list.
    const ArcadeRomRule rules[]={{264,0,3,1},{264,0,4,8},{281,0,3,4}};
    const uint16_t order[]={0,1,2};
    std::fill(memory.begin(),memory.end(),0);
    uint8_t *ram=memory.data()+0xa000;
    ram[14]=8;ram[15]=2;
    ram[0xe0]=0x81;ram[0xe1]=1;ram[0xe2]=3;ram[0xed]=20;
    for(unsigned branch : {0U,8U,65535U}) {
        ram[0x16]=branch>>8;ram[0x35]=branch&255;
        auto move=arcade_select_rom_move(nullptr,nullptr,0,rules,order,3,ram,5000,true);
        assert(move.controls==1 && move.ready);
    }
    ram[0xec]=12;
    auto future=arcade_select_rom_move(nullptr,nullptr,0,rules,order,3,ram,0,false);
    assert(future.controls==1 && !future.ready);
    ram[0xec]=0;ram[0xe0]=0x88;ram[0xe2]=4;
    auto alternate=arcade_select_rom_move(nullptr,nullptr,0,rules,order,3,ram,0,false);
    assert(alternate.controls==8 && alternate.ready);
    ram[0xe2]=99;
    assert(!arcade_select_rom_move(nullptr,nullptr,0,rules,order,3,ram,0,false).controls);
    const ArcadeRomRule wait[]={{264,0,3,0},{264,0,4,8}};
    const uint16_t wait_order[]={0,1};ram[0xe2]=4;
    assert(!arcade_select_rom_move(nullptr,nullptr,0,wait,wait_order,2,ram,0,false).controls);
    // A retry-only DL1 state publishes a preview for automation, but neither
    // visual text nor the audio event may announce it before readiness.
    std::fill(memory.begin(),memory.end(),0);
    ram=memory.data()+0xa000;
    ram[14]=8;ram[15]=2;ram[0xe0]=0x81;ram[0xe1]=1;ram[0xe2]=3;
    ram[0xed]=20;ram[0xec]=12;
    arcade_configure_guidance(1,true,false);
    arcade_guidance_cine(memory.data(),memory.size(),"dle21",true,5000);
    assert((arcade_guidance_snapshot()&31)==1);
    assert(!(arcade_guidance_snapshot()&256) && !arcade_visual_controls());
    const uint64_t before=arcade_guidance_snapshot()>>32;
    ram[0xec]=0;
    arcade_guidance_cine(memory.data(),memory.size(),"dle21",true,5000);
    assert(arcade_visual_controls()==1 && (arcade_guidance_snapshot()&256));
    assert((arcade_guidance_snapshot()>>32)==before+1);
    arcade_guidance_cine(memory.data(),memory.size(),"dle21",true,5000);
    assert((arcade_guidance_snapshot()>>32)==before+1);
    arcade_guidance_cine(memory.data(),memory.size(),"dle21",false,5000);
    assert(!arcade_visual_controls());
    // SAE 1.0 scene 2/step 1: its first RIGHT is a necessary zero-score
    // transition. Exercise the production ROM catalog, not the A3 alias.
    std::fill(memory.begin(),memory.end(),0);
    ram=memory.data()+0xa000;
    ram[14]=2;ram[15]=1;ram[0xe0]=0x88;ram[0xe1]=1;ram[0xe2]=2;ram[0xed]=30;
    arcade_configure_guidance(1,false,true);
    arcade_guidance_cine(memory.data(),memory.size(),"sae",true,1287);
    assert(arcade_visual_controls()==8 && (arcade_guidance_snapshot()&256));
    arcade_guidance_cine(memory.data(),memory.size(),"unknown",true,1287);
    assert(!arcade_visual_controls());
    puts("Guidance: bounds, retry signatures, native DL2 moves and unknown-state refusal passed");
}
