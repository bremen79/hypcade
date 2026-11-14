/* Hypcade: Copyright (C) 2026 Francesco Orabona.
 * PR-7820 protocol adapted from DAPHNE's src/ldp-in/pr7820.cpp:
 * Copyright (C) 2003 Warren Ondras; based on work by Matt Ownby and Mark
 * Broadhead. Original license: GPL-2.0-or-later, without warranty.
 * This adaptation is distributed under GPL-3.0-or-later.
 * The pinned laser-vault board source and its notices remain unchanged.
 */
#define cine_load_roms cine_load_original_roms
#define cine_reset cine_reset_original
#include "vendor/src/games/cinematronics/board.c"
#undef cine_load_roms
#undef cine_reset
#include "offline_board.h"

/* Both parallel players use the same digit/audio/transport registers. PR-7820
 * differs in its ready line and immediate writes, with no LD-V1000 strobes. */
static void pr_write(void *ctx,uint64_t now,uint8_t value) {
    Ldv1000 *p=ctx;ldv1000_update(p,now);
    static const uint8_t digits[]={0x3f,0x0f,0x8f,0x4f,0x2f,0xaf,0x6f,0x1f,0x9f,0x5f};
    for(unsigned i=0;i<10;i++)if(value==digits[i]) {
        if(p->digit_count==5){memmove(p->digits,p->digits+1,4);p->digit_count=4;}
        p->digits[p->digit_count++]=(uint8_t)i;return;
    }
    int frame=0;
    for(int i=0;i<p->digit_count;i++)frame=frame*10+p->digits[i];
    switch(value) {
    case 0xf7:ldp_search(p->ldp,frame);p->digit_count=0;break;
    case 0xfd:ldp_play(p->ldp);break;
    case 0xfb:ldp_pause(p->ldp);break;
    case 0xa3:ldp_set_speed(p->ldp,1);break;
    case 0xf3:p->autostop_frame=frame;p->digit_count=0;ldp_play(p->ldp);break;
    case 0xf4:case 0xfc: {
        unsigned channel=value==0xfc;
        p->audio[channel]=p->digit_count ? (p->digits[0]&1)!=0 : !p->audio[channel];
        p->digit_count=0;break;
    }
    case 0xf9:case 0xff:break; // Matches Hypseus's ignored Reject/No entry.
    default:fprintf(stderr,"Unsupported PR-7820 command %02x\n",value);break;
    }
    p->last_command=value;
}
static uint8_t pr_status(void *ctx,uint64_t now) {(void)ctx;(void)now;return 255;}
static bool pr_status_strobe(void *ctx,uint64_t now) {(void)ctx;(void)now;return false;}
static bool pr_busy(void *ctx,uint64_t now) {
    Ldv1000 *p=ctx;ldv1000_update(p,now);
    return p->ldp->state==LDP_SEARCHING || p->ldp->state==LDP_STOPPED;
}
CineLaserdisc offline_pr7820_link(Ldv1000 *p) {
    return (CineLaserdisc){p,pr_status,pr_write,pr_status_strobe,pr_busy};
}
static void pr_mem_write(void *ctx,uint16_t address,uint8_t value) {
    CineBoard *b=ctx;
    if(address>=0xe000) {
        if((address&0x38)==0x20){b->laserdisc.send_command(b->laserdisc.ctx,b->cycles,value);return;}
        if((address&0x38)==0x08){b->misc=value;return;}
    }
    mem_write(ctx,address,value);
}
void cine_reset(CineBoard *b,CineLaserdisc player) {
    cine_reset_original(b,player);
    if(b->game==CINE_PR7820) {
        b->laserdisc=offline_pr7820_link(player.ctx);
        b->cpu.bus.write=pr_mem_write;
    }
}

bool cine_load_roms(CineBoard *b,const char *path) {
    const OfflineRom *rom=NULL;
    for(unsigned i=0;i<sizeof offline_roms/sizeof *offline_roms;i++)
        if(offline_roms[i].pr7820 && roms_has(path,offline_roms[i].names[0])){rom=offline_roms+i;break;}
    if(!rom)return cine_load_original_roms(b,path);
    memset(b->rom,255,sizeof b->rom);
    for(unsigned i=0;i<rom->chips;i++) {
        uint8_t *bytes=NULL;size_t size=0;
        if(!roms_read(path,rom->names[i],&bytes,&size))return false;
        bool valid=size==8192 && crc32(0,bytes,(uInt)size)==rom->crc[i];
        if(valid)memcpy(b->rom+i*8192,bytes,size);
        free(bytes);
        if(!valid){fprintf(stderr,"Unsupported ROM chip: %s\n",rom->names[i]);return false;}
    }
    b->game=CINE_PR7820;b->switches=&dragons_lair_switches;
    b->dsw1=rom->dsw1;b->dsw2=rom->dsw2;
    printf("ROMs: %s (PR-7820)\n",rom->game);return true;
}
