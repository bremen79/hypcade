/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef HYPCADE_ARCADE_MOVE_POLICY_H
#define HYPCADE_ARCADE_MOVE_POLICY_H
#include "arcade_signature.h"
#include <stdbool.h>

typedef struct {
    uint8_t controls;
    bool ready;
    uint64_t window;
} ArcadeMoveSelection;

/* Ace A3 can require different inputs with an identical visible move table.
 * A035.3 was verified by controlled replay to change UP versus horizontal
 * acceptance. A016 also distinguishes difficulty/progress contexts. Preserve
 * both complete state bytes in the key, without hashing the rest of RAM or
 * changing the compact record size. Scene-transition detection stays separate. */
static inline uint64_t arcade_move_signature(const uint8_t *table, size_t size, uint16_t branch) {
    uint64_t signature = arcade_cine_signature(table, size);
    if (branch) {
        signature = (signature ^ 0xb4) * UINT64_C(1099511628211);
        signature = (signature ^ (branch & 255)) * UINT64_C(1099511628211);
        signature = (signature ^ (branch >> 8)) * UINT64_C(1099511628211);
    }
    return signature;
}

/* ROM scene/step identity is also used by the host replay audit. */
static inline uint32_t arcade_rom_state(unsigned scene,unsigned step,uint16_t branch) {
    return (scene&127U) | ((step&127U)<<7) | ((uint32_t)branch<<14);
}

/* Complete ROM policies: no sampled branch bytes or absolute video frames.
 * The ROM loads/filters entries and executes its current difficulty rules.
 * Match their control, local window and outcome, never their ROM ordinal. */
typedef struct {
    uint16_t state;
    uint8_t window,outcome,control;
} ArcadeRomRule;

/* Contextual local-cost + exit-cost policies. Each two-bit context field
 * stores skill (0..2, 3=any), replay (0/1, 2=any), score gate (0/1, 2=any).
 * A3's loader can filter descriptors: slot=255 searches its loaded list.
 * SAE pins slot and header to distinguish its score-restoring descriptors. */
typedef struct {
    uint16_t state;
    uint8_t context,slot,window,header,outcome,control;
} ArcadeCostRule;

static inline ArcadeMoveSelection arcade_select_cost_move(
        const ArcadeCostRule *rules,const uint16_t *order,size_t count,
        const uint8_t *ram) {
    ArcadeMoveSelection result={0,false,0};
    unsigned state=arcade_rom_state(ram[14],ram[15],0);
    size_t low=0,high=count;
    while(low<high){size_t mid=low+(high-low)/2;
        if(rules[order[mid]].state<state)low=mid+1;else high=mid;}
    for(size_t i=low;i<count && rules[order[i]].state==state;i++) {
        const ArcadeCostRule *r=rules+order[i];
        unsigned skill=r->context&3,replay=(r->context>>2)&3,gate=(r->context>>4)&3;
        if((skill!=3 && skill!=ram[0xd4]) ||
           (replay!=2 && replay!=((ram[0x35]>>3)&1)) ||
           (gate!=2 && gate!=((ram[10]>>1)&1)))continue;
        if(!r->control)return result;
        if(r->control!=1 && r->control!=2 && r->control!=4 && r->control!=8 && r->control!=16)continue;
        for(unsigned slot=0;slot<16;slot++) {
            const uint8_t *x=ram+0xe0+16*slot;
            if(!(x[0]&128))break;
            unsigned w=r->window,control=(x[0]&15)?(x[0]&15):16;
            if((r->slot!=255 && r->slot!=slot) || (r->header && r->header!=x[0]) ||
               control!=r->control || w>=(x[1]&3) || !x[13+w] ||
               x[2+((x[1]>>(2+2*w))&3)]!=r->outcome)continue;
            unsigned delay=x[12];for(unsigned j=0;j<w;j++)delay+=x[13+j];
            if(delay>12)return result;
            result.controls=control;result.ready=delay==0;
            result.window=((uint64_t)r->context<<48)|((uint64_t)state<<32)|
                          ((uint64_t)(slot*3+w+1)<<8)|r->outcome;
            return result;
        }
    }
    return result;
}

static inline ArcadeMoveSelection arcade_select_rom_move(
        const ArcadeRomRule *rules,const uint16_t *rule_order,size_t rule_count,
        const uint8_t *ram) {
    ArcadeMoveSelection result={0,false,0};
    unsigned state=arcade_rom_state(ram[14],ram[15],0);
    size_t low=0,high=rule_count;
    while(low<high){size_t mid=low+(high-low)/2;if(rules[rule_order[mid]].state<state)low=mid+1;else high=mid;}
    for(size_t i=low;i<rule_count && rules[rule_order[i]].state==state;i++) {
        const ArcadeRomRule *rule=rules+rule_order[i];
        if(!rule->control)return result; /* This objective deliberately waits. */
        for(unsigned e=0;e<16;e++) {
            const uint8_t *x=ram+0xe0+16*e;
            if(!(x[0]&128))break;
            unsigned control=(x[0]&15) ? (x[0]&15) : 16;
            unsigned w=rule->window;
            if(control!=rule->control || w>=(x[1]&3) || !x[13+w] ||
               x[2+((x[1]>>(2+2*w))&3)]!=rule->outcome)continue;
            unsigned delay=x[12];for(unsigned p=0;p<w;p++)delay+=x[13+p];
            /* A loaded preferred alternative remains preferred before it opens;
             * do not select a lower-ranked action just because it opens first. */
            if(delay>12)return result;
            result.controls=control;result.ready=delay==0;
            result.window=((uint64_t)state<<32)|((uint64_t)(e*3+w+1)<<8)|rule->outcome;
            return result;
        }
    }
    return result;
}

#endif
