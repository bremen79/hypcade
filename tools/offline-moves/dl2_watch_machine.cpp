/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
// SPDX-License-Identifier: GPL-3.0-or-later
// Headless adapter around the original Hypseus i86, DL2 ports and Sony protocol.
// Driver methods are generated unchanged from lair2.cpp; no ROM moves are supplied.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdarg>
#include <cmath>
#include <deque>
#include <algorithm>
#include <string>
#include <SDL3/SDL.h>
#include <jni.h>
#include <zlib.h>
#undef OF
#include "../../android/app/jni/arcade_guidance.h"
#include <plog/Log.h>
#define GAME_H
#define LDP_PRE_H
#define BITMAP_H
#define HYPSEUS_H
#define FRAME_SIZE 5
#define FRAME_ARRAY_SIZE 6
#define NUM_COIN_SLOTS 2
#define DL2_BUF_SIZE 1024
#define DL2_IER 1
#define DL2_IIR 2
#define DL2_LCR 3
#define DL2_MCR 4
#define DL2_LSR 5
#define DL2_MSR 6
#define DL2_CTS 0x10
#define DL2_DSR 0x20
static uint8_t ram[1<<20];
static uint64_t machine_cycles=0;
static bool quit=false;
void set_quitflag() {quit=true;}
namespace sound { void write_ctrl_data(int,int,int) {} void play(int) {} }
static int g_sound_map[100]={0};
static const bool g_dl2_euro=false;
static const int g_dl2_ver=6;
enum { SWITCH_UP,SWITCH_DOWN,SWITCH_LEFT,SWITCH_RIGHT,SWITCH_BUTTON1,SWITCH_BUTTON2,SWITCH_BUTTON3,SWITCH_COIN1,SWITCH_START1,SWITCH_PAUSE,SWITCH_EXIT,SWITCH_SERVICE,SWITCH_START2,SWITCH_COIN2 };
static int g_dl2_irq_val=0;
class Dl2Machine { public:
 uint8_t (&m_cpumem)[1<<20]=ram;
 const char *m_shortgamename="lair2";
 bool m_bSerialHack=false,m_video_overlay_needs_update=false,m_game_uses_video_overlay=false;
 void update_android_scoreboard() {}
 uint8_t banks[2]={255,1};
 unsigned m_uSerialBufSize=0,m_uCoinCount[2]={0,0};
 bool m_serial_int_enabled=false,m_prefer_samples=false,m_sample_trigger=false;
 int m_soundchip_id=0;
 uint8_t m_u8SerialBuf[1024]={0},m_port61_val=0;
 uint16_t EEPROM_9536[128]={0};
 uint8_t cpu_mem_read(uint32_t p) { return ram[p&0xfffff]; }
 void cpu_mem_write(uint32_t,uint8_t);
 void do_irq(unsigned);
 void input_enable(uint8_t,int8_t);
 void input_disable(uint8_t,int8_t);
 uint8_t port_read(uint16_t);
 void port_write(uint16_t,uint8_t);
 void EEPROM_9536_write(uint8_t);
 void update_pc(uint32_t) {}
 const char *get_shortgamename() {return m_shortgamename;}
 SDL_Surface *get_active_video_overlay() {return nullptr;}
 void set_video_overlay_needs_update(bool) {}
 void blit() {}
};
static Dl2Machine board;
static Dl2Machine *g_game=&board;
enum {LDP_ERROR,LDP_SEARCHING,LDP_STOPPED,LDP_PLAYING,LDP_PAUSED};
class Player { public:
 int status=LDP_PLAYING,frame=0,target=0;
 double fraction=0; uint64_t last=0,seek_at=UINT64_MAX;
 unsigned seek_ms=0;
 void update() {
  if(status==LDP_SEARCHING && machine_cycles>=seek_at) {status=LDP_PAUSED;frame=target;fraction=0;seek_at=UINT64_MAX;}
  if(status==LDP_PLAYING) {fraction+=(machine_cycles-last)*29.97/10000000.;unsigned d=(unsigned)fraction;frame+=d;fraction-=d;}
  last=machine_cycles;
 }
 int get_current_frame() {return frame;}
 int get_status() {return status;}
 void pre_play() {last=machine_cycles;status=LDP_PLAYING;}
 void pre_pause() {status=LDP_PAUSED;}
 bool pre_search(char *s,bool) {target=atoi(s);status=LDP_SEARCHING;seek_at=machine_cycles+seek_ms*10000ULL;return true;}
 unsigned get_discvideo_width() {return 640;}
 void disable_audio1() {} void disable_audio2() {} void enable_audio1() {} void enable_audio2() {}
};
static Player player;
static Player *g_ldp=&player;
namespace cpu {
 static uint64_t event_at=UINT64_MAX;static void (*event)(void*)=nullptr;static void *arg;
 Uint32 get_hz(int) {return 10000000;}
 void set_event(int,unsigned delay,void(*f)(void*),void *a) {event_at=machine_cycles+delay;event=f;arg=a;}
}
namespace video {const int OVERLAY_LDP1450_LINE_SPACING=10;template<class... T> void draw_singleline_LDP1450(T...) {} }
namespace vp932 {void write(uint8_t) {} bool data_available() {return false;} uint8_t read() {return 0;} }
#include "../../src/cpu/x86/i86.cpp"
uint8_t *OP_ROM=ram,*OP_RAM=ram;
offs_t memory_amask=0xfffff;
int mame_debug=0;
void printline(const char *,...) {}
void logerror(const char *,...) {}
unsigned char cpu_getactivecpu() {return 0;}
std::string fmt(const std::string format,...) {char buf[512];va_list a;va_start(a,format);vsnprintf(buf,sizeof buf,format.c_str(),a);va_end(a);return buf;}
#include "../../src/ldp-in/ldp1000.cpp"
#include "dl2_driver.inc"
#include "../../android/app/jni/arcade_guidance.h"
static unsigned word(unsigned offset) {return ram[0x10000+offset]|(ram[0x10001+offset]<<8);}
static unsigned irq_count[256]={0};
static int irq_callback(int) {++irq_count[g_dl2_irq_val];i86_set_irq_line(0,CLEAR_LINE);return g_dl2_irq_val;}

struct QueuedInput {int action;bool down;};
static std::deque<QueuedInput> input_queue;
static uint64_t elapsed_ms;
static unsigned irq_ticks[2]={0,0},pending_irq[2]={0,0};
static unsigned input_phase,initial_lives,losses,moves_count;
static bool started,finished,failed;
static unsigned final_record,final_frame;
static unsigned omit_move,omitted;
static unsigned score() {return word(0x56b0)/10;}

extern "C" JNIEXPORT jboolean JNICALL Java_org_hypseus_android_HypseusActivity_nativeEmulatorReady(JNIEnv*,jclass) {
 return elapsed_ms>=17;
}
extern "C" JNIEXPORT void JNICALL Java_org_hypseus_android_HypseusActivity_nativeArcadeInput(JNIEnv*,jclass,jint action,jboolean down) {
 if(started && down && action<5 && !omitted &&
    ((omit_move==1 && moves_count==0) ||
     (omit_move==2 && word(0x5694+2*(word(0x56aa)&63))==final_record))) {
  ++omitted;return;
 }
 if(getenv("HYPCADE_WATCH_TRACE"))fprintf(stderr,"JAVA ms=%llu action=%d down=%d frame=%u oldmask=%u pc=%x\n",(unsigned long long)elapsed_ms,action,down,word(0xa158),word(0xa1f0),i86_get_pc());
 input_queue.push_back({action,down!=0});
}
extern "C" JNIEXPORT jboolean JNICALL Java_org_hypseus_android_NativeRomMachine_init(JNIEnv *env,jclass,jstring path,jint level,jint seek,jint phase,jint omit) {
 const char *filename=env->GetStringUTFChars(path,nullptr);
 FILE *rom=fopen(filename,"rb");env->ReleaseStringUTFChars(path,filename);
 if(!rom || fread(ram+0xf0000,1,65536,rom)!=65536) {if(rom)fclose(rom);return false;}fclose(rom);
 if(crc32(0,ram+0xf0000,65536)!=0xe9453a1b || level<0 || level>4 || seek<0 || phase<0 || phase>16)return false;
 for(unsigned i=0;i<60;i++)board.EEPROM_9536[i]=ram[0xf9c14+2*i]|(ram[0xf9c15+2*i]<<8);
 board.EEPROM_9536[14]=level;player.seek_ms=seek;input_phase=phase;omit_move=omit;
 // Derive the completion clip from the last exit record in this revision's table.
 for(unsigned i=0;i<1200;i++)if(ram[0xf5a24+14*i]==5) {
  final_record=i;final_frame=ram[0xf5a28+14*i]|(ram[0xf5a29+14*i]<<8);
 }
 ram[0xf2804]=ram[0xf2805]=0x90;patch_driver();
 arcade_configure_guidance(1,false,true);
 i86_init();i86_reset();i86_set_irq_callback(irq_callback);i86_set_pc(0xffff0);ldp1000::reset();
 return true;
}
extern "C" JNIEXPORT void JNICALL Java_org_hypseus_android_NativeRomMachine_advanceTo(JNIEnv*,jclass,jlong target) {
 while(elapsed_ms<(uint64_t)target && !quit && !finished && !failed) {
  ++elapsed_ms;uint64_t boundary=elapsed_ms*10000ULL;
  while(machine_cycles<boundary) {
   uint64_t until=std::min(boundary,cpu::event_at);
   if(until>machine_cycles)machine_cycles+=i86_execute((unsigned)(until-machine_cycles));
   if(machine_cycles>=cpu::event_at) {auto f=cpu::event;cpu::event_at=UINT64_MAX;if(f)f(cpu::arg);}
  }
  // Match cpu.cpp: 1ms interleaving, rounded microperiods, one IRQ per ms,
  // timer before serial; deferred serial IRQs remain pending.
  const unsigned periods[]={54945,938};
  for(unsigned i=0;i<2;i++) {
   if(elapsed_ms>((uint64_t)(irq_ticks[i]+1)*periods[i])/1000) {++irq_ticks[i];++pending_irq[i];}
  }
  for(unsigned i=0;i<2;i++)if(pending_irq[i]) {board.do_irq(i);--pending_irq[i];break;}
  player.update();
  // Match SDL_check_input's >16ms throttle, not immediate switch mutation.
  if((elapsed_ms+input_phase)%17==0) {
   while(!input_queue.empty()) {
    auto input=input_queue.front();input_queue.pop_front();
    if(getenv("HYPCADE_WATCH_TRACE"))fprintf(stderr,"DELIVER ms=%llu action=%d down=%d frame=%u oldmask=%u pc=%x\n",(unsigned long long)elapsed_ms,input.action,input.down,word(0xa158),word(0xa1f0),i86_get_pc());
    if(input.down)board.input_enable(input.action,-1);else board.input_disable(input.action,-1);
    if(started && input.down && input.action<5)++moves_count;
   }
  }
  unsigned lives=word(0x56ac);
  if(!started && lives>0 && lives<=9) {started=true;initial_lives=lives;}
  if(started) {
   unsigned record=word(0x5694+2*(word(0x56aa)&63));
   if(lives<initial_lives) {++losses;failed=true;}
   // A death seek can also pass the ending's frame number. Require the actual
   // final record and its end boundary, with every starting life intact.
   if(!failed && record==final_record && lives==initial_lives &&
      player.status==LDP_PLAYING && player.frame>=(int)final_frame &&
      player.frame<=(int)final_frame+2)finished=true;
  }
 }
}
extern "C" JNIEXPORT jint JNICALL Java_org_hypseus_android_NativeRomMachine_status(JNIEnv*,jclass) {
 return finished?1:failed?-1:quit?-2:0;
}
extern "C" JNIEXPORT jstring JNICALL Java_org_hypseus_android_NativeRomMachine_summary(JNIEnv *env,jclass) {
 char text[512];snprintf(text,sizeof text,"{\"complete\":%s,\"no_life_loss\":%s,\"moves\":%u,\"score\":%u,\"lives\":%u,\"milliseconds\":%llu,\"frame\":%u,\"actual_frame\":%d,\"record\":%u,\"opens\":%u,\"closes\":%u,\"pc\":%u,\"losses\":%u,\"omitted\":%u}",
  finished?"true":"false",losses?"false":"true",moves_count,score(),word(0x56ac),(unsigned long long)elapsed_ms,word(0xa158),player.frame,word(0x5694+2*(word(0x56aa)&63)),word(0xa160),word(0xa15a),i86_get_pc(),losses,omitted);
 return env->NewStringUTF(text);
}
