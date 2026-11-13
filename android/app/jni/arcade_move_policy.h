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

/* ROM scene/step identity avoids confusing equal prompt shapes in different
 * scenes. Ace's complete branch bytes remain part of the key. */
typedef struct {
    uint32_t state,frame;
    uint16_t timing;
    uint8_t outcome,control;
} ArcadeRomMove;

static inline uint32_t arcade_rom_state(unsigned scene,unsigned step,uint16_t branch) {
    return (scene&127U) | ((step&127U)<<7) | ((uint32_t)branch<<14);
}

static inline ArcadeMoveSelection arcade_select_rom_move(const ArcadeRomMove *moves,const uint16_t *order,size_t count,
        const uint8_t *ram,unsigned frame,bool ace) {
    ArcadeMoveSelection result={0,false,0};
    uint16_t branch=ace ? (uint16_t)((ram[0x16]<<8)|ram[0x35]) : 0;
    uint32_t state=arcade_rom_state(ram[14],ram[15],branch);
    size_t low=0,high=count;
    while(low<high){size_t mid=low+(high-low)/2;if(moves[order[mid]].state<state)low=mid+1;else high=mid;}
    for(size_t i=low;i<count && moves[order[i]].state==state;i++) {
        const ArcadeRomMove *move=moves+order[i];
        unsigned slot=(move->timing>>8)&63,entry=slot/3,window=slot%3,ticks=move->timing&255;
        if(entry>=16 || !ticks)continue;
        const uint8_t *x=ram+0xe0+entry*16;
        unsigned control=(x[0]&15) ? (x[0]&15) : 16;
        if(!(x[0]&128) || window>=(x[1]&3) || control!=move->control ||
           x[2+((x[1]>>(2+2*window))&3)]!=move->outcome || !x[13+window])continue;
        unsigned delay=x[12];for(unsigned w=0;w<window;w++)delay+=x[13+w];
        unsigned end=move->frame+(ticks*786U+999U)/1000U+2;
        if(delay>12 || frame+10<move->frame || frame>end)continue;
        bool ready=!delay && frame>=move->frame && x[13+window]<=ticks;
        if(!ready && result.controls)continue;
        result.controls=move->control;result.ready=ready;
        result.window=((uint64_t)state<<32)|((uint64_t)(slot+1)<<8)|move->outcome;
        if(ready)return result;
    }
    return result;
}
#endif
