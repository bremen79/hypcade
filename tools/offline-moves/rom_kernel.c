/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Small original-ROM subroutine audit. No media, interrupts or CPU snapshots. */
#include "cpu/z80.h"
#include <stdint.h>
#include <string.h>
static uint8_t rom[65536], mem[65536], accessed[1024], modified[1024];
static Z80 cpu;
static uint16_t observations[128];
static unsigned observation_count;
static unsigned input_port=256;
static uint8_t rd(void *ctx,uint16_t a) {
 (void)ctx;
 if(a==0xc008 && input_port<256)return (uint8_t)input_port;
 if(a>=0xa000&&a<0xa400)accessed[a-0xa000]=1;
 /* Observe opcode fetches only. The second ED opcode fetch increments R
  * once more before LD A,R reads it. Observation never changes execution. */
 if(mem[a]==0xed && mem[(uint16_t)(a+1)]==0x5f && cpu.pc==(uint16_t)(a+1)) {
  if(observation_count<64) {
   observations[2*observation_count]=a;
   observations[2*observation_count+1]=(cpu.r&128)|((cpu.r+1)&127);
  }
  ++observation_count;
 }
 return mem[a];
}
static void wr(void *ctx,uint16_t a,uint8_t v) {(void)ctx;mem[a]=v;if(a>=0xa000&&a<0xa400)modified[a-0xa000]=1;}
static uint8_t in(void *ctx,uint16_t p) {(void)ctx;(void)p;return 255;}
static void out(void *ctx,uint16_t p,uint8_t v) {(void)ctx;(void)p;(void)v;}
void rom_init(const uint8_t *data,unsigned size) {memset(rom,0,sizeof rom);if(size<=sizeof rom)memcpy(rom,data,size);}
void rom_inputs(unsigned value) {input_port=value;}
unsigned rom_call(uint8_t *ram,unsigned pc,unsigned stop,unsigned de,unsigned hl,unsigned bc,unsigned iy,unsigned ix,unsigned refresh,uint16_t *result) {
 memcpy(mem,rom,sizeof mem);memcpy(mem+0xa000,ram,1024);
 memset(accessed,0,sizeof accessed);memset(modified,0,sizeof modified);
 observation_count=0;
 z80_init(&cpu,(Z80Bus){0,rd,wr,in,out});cpu.pc=pc;cpu.sp=0xa3f0;cpu.r=refresh;
 cpu.d=de>>8;cpu.e=de;cpu.h=hl>>8;cpu.l=hl;cpu.b=bc>>8;cpu.c=bc;cpu.iyh=iy>>8;cpu.iyl=iy;
 cpu.ixh=ix>>8;cpu.ixl=ix;
 cpu.d2=0xa0;cpu.e2=0x30;
 mem[0xa3f0]=0xad;mem[0xa3f1]=0xde;
 unsigned n=0;while(cpu.pc!=stop&&n<10000){z80_step(&cpu);++n;}
 memcpy(ram,mem+0xa000,1024);
 result[0]=cpu.b<<8|cpu.c;result[1]=cpu.h<<8|cpu.l;result[2]=cpu.d<<8|cpu.e;result[3]=cpu.r;result[4]=cpu.a;result[5]=cpu.pc;
 return cpu.pc==stop?n:0;
}
void rom_access(uint8_t *readset,uint8_t *writeset) {memcpy(readset,accessed,1024);memcpy(writeset,modified,1024);}
unsigned rom_observations(uint16_t *result) {
 if(observation_count>64)return observation_count;
 memcpy(result,observations,2*observation_count*sizeof(uint16_t));return observation_count;
}
