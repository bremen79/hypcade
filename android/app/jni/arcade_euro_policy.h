/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "arcade_move_policy.h"

/* European fixed-record tables have 16-bit targets (bit 15 requests an
 * immediate transition). Keep these separate from Cine's compact byte targets. */
typedef struct { uint16_t record, target; uint8_t control; } ArcadeEuroRule;

static inline ArcadeMoveSelection arcade_select_euro_move(
        const ArcadeEuroRule *rules, const uint16_t *order, size_t count,
        const uint8_t *memory, size_t size, unsigned frame) {
    ArcadeMoveSelection result={0,false,0};
    if(size<0xa28a)return result;
    const uint8_t *ram=memory+0xa000;
    unsigned record=ram[0x17a]|(ram[0x17b]<<8);
    if(!record || record>704 || (ram[0x111]&0x50))return result;
    const uint8_t *rom=memory+0x2088+(record-1)*32;
    unsigned start=rom[0]|(rom[1]<<8);
    // A17A is published before all record fields have finished loading.
    if((unsigned)(ram[0x10f]|(ram[0x110]<<8))!=start || frame<start || frame>start+rom[3]+1)
        return result;
    size_t low=0,high=count;
    while(low<high){size_t mid=low+(high-low)/2;if(rules[order[mid]].record<record)low=mid+1;else high=mid;}
    for(size_t i=low;i<count && rules[order[i]].record==record;i++) {
        const ArcadeEuroRule *rule=rules+order[i];
        if(!rule->control)return result; // Deliberate wait is a ranked choice.
        unsigned bit=0;
        while(bit<5 && rule->control!=(1U<<bit))++bit;
        if(bit==5)continue;
        unsigned slot=7-bit;
        if((ram[0x115+2*slot]|(ram[0x116+2*slot]<<8))!=rule->target)continue;
        // ROM uses CP followed by RET M, not an unsigned comparison. Preserve
        // its wraparound/sign semantics and the full immediate-target bit.
        unsigned remaining=ram[0x112],cutoff=ram[0x189+(ram[0x152] ? 0x100 : 0)];
        if(!remaining || ((remaining-cutoff)&128))return result;
        result.controls=rule->control;result.ready=true;
        result.window=((uint64_t)record<<32)|((uint64_t)start<<16)|rule->target;
        return result;
    }
    return result;
}
