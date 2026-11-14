/* Hypcade: Copyright (C) 2026 Francesco Orabona.
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Runs the original Mark Broadhead/DirtBagXon European driver and Mark Broadhead
 * VP932 protocol methods extracted at build time, retaining their source notices.
 * Video, sound and real-time waits are omitted; CPU/CTC/DART methods are unchanged.
 */
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <queue>
#include <string>
#include <iostream>
#include <algorithm>
#include <vector>
#include "arcade_euro_policy.h"
extern "C" {
#include "cpu/z80.h"
#include "ldp/ldp.h"
}
using namespace std;
using Uint8=uint8_t;using Uint16=uint16_t;using Uint32=uint32_t;using Sint8=int8_t;
struct NullLog {template<class T>NullLog &operator<<(const T&){return *this;}};static NullLog null_log;
#define LOGD null_log
#define LOGW null_log
#define LOGE null_log
static std::string fmt(const char*,...){return {};}
#define COUNTER true
#define TIMER false
#define LAIREURO_SPLASH 5
#define LAIREURO_CPU_HZ 3579545
#define MAX_COMMAND_SIZE 31
static uint64_t now_cycles;
struct ctc_channel {double trig;Uint8 control,time_const;bool load_const,time,time_trig,clk_trig_section;Uint16 prescaler;bool mode,interrupt;};
struct ctc_chip {Uint8 int_vector;ctc_channel channels[4];double clock;};
struct dart_chip {Uint8 next_reg,int_vector;bool transmit_int,ext_int;};
static ctc_chip g_ctc;static dart_chip g_dart;static Uint8 g_int_vec,g_soundchip_id;
static double irq_period[4],irq_next[4];
namespace cpu {static void change_irq(int,unsigned,double);}
namespace palette {static void set_yuv_transparency(bool){}}
namespace sound {static void write_ctrl_data(int,unsigned,int){}}
namespace vp932 {void process_command();void restoreAudio();Uint8 read();void write(Uint8);bool data_available();}
enum {SWITCH_UP,SWITCH_DOWN,SWITCH_LEFT,SWITCH_RIGHT,SWITCH_BUTTON1,SWITCH_BUTTON2,SWITCH_BUTTON3,SWITCH_COIN1,SWITCH_START1,SWITCH_PAUSE,SWITCH_EXIT,SWITCH_SERVICE,SWITCH_START2,SWITCH_COIN2};
struct EuroMachine {
 Uint8 m_cpumem[65536]{},m_banks[4]{255,255,0xdf,0xef},m_wt_misc=0;bool m_splash=false,m_video_overlay_needs_update=false;Z80 z80{};
 void blit(){};void do_irq(Uint32);void do_nmi();Uint8 cpu_mem_read(Uint16);void cpu_mem_write(Uint16,Uint8);void port_write(Uint16,Uint8);Uint8 port_read(Uint16);void input_enable(Uint8,Sint8);void input_disable(Uint8,Sint8);
};
static EuroMachine machine;
#define Z80_GET_PC machine.z80.pc
#define Z80_ASSERT_IRQ do {machine.z80.irq=true;machine.z80.irq_data=g_int_vec;}while(0)
static constexpr LdpState StateSearching=LDP_SEARCHING, StateStopped=LDP_STOPPED, StatePlaying=LDP_PLAYING, StatePaused=LDP_PAUSED;
enum {PLAYER_ERROR,PLAYER_SEARCHING,PLAYER_STOPPED,PLAYER_PLAYING,PLAYER_PAUSED};
#define LDP_ERROR PLAYER_ERROR
#define LDP_SEARCHING PLAYER_SEARCHING
#define LDP_STOPPED PLAYER_STOPPED
#define LDP_PLAYING PLAYER_PLAYING
#define LDP_PAUSED PLAYER_PAUSED
struct Player {
 Ldp player{};uint64_t last=0;
 Player(){ldp_init(&player,25,0);}
 void update(){ldp_update(&player,double(now_cycles-last)/3579545.0);last=now_cycles;}
 int get_current_frame(){update();return player.frame;}
 int get_status(){update();switch(player.state){case StateSearching:return PLAYER_SEARCHING;case StateStopped:return PLAYER_STOPPED;case StatePlaying:return PLAYER_PLAYING;case StatePaused:return PLAYER_PAUSED;}return PLAYER_ERROR;}
 bool pre_search(const char *s,bool){update();ldp_search(&player,atoi(s));return true;}
 void pre_play(){update();ldp_play(&player);}void pre_pause(){update();ldp_pause(&player);}
 void enable_audio1(){}void enable_audio2(){}void disable_audio1(){}void disable_audio2(){}
};
static Player player;static Player *g_ldp=&player;
static void ctc_write(Uint8,Uint8);static Uint8 ctc_read(Uint8);static void dart_write(bool,bool,Uint8);static void ctc_init(double,double,double,double,double);static void ctc_update_period(Uint8);
namespace cpu {static void change_irq(int,unsigned channel,double ms){irq_period[channel]=ms*3579.545;irq_next[channel]=irq_period[channel]>0?now_cycles+irq_period[channel]:1e30;}}
#include "euro_player.inc"
#include "euro_driver.inc"
static uint8_t mem_read(void*ctx,uint16_t at){return ((EuroMachine*)ctx)->cpu_mem_read(at);}
static void mem_write(void*ctx,uint16_t at,uint8_t v){((EuroMachine*)ctx)->cpu_mem_write(at,v);}
static uint8_t port_read(void*ctx,uint16_t p){return ((EuroMachine*)ctx)->port_read(p);}
static void port_write(void*ctx,uint16_t p,uint8_t v){((EuroMachine*)ctx)->port_write(p,v);}
struct Input {uint64_t cycle;unsigned action,down;};
int main(int argc,char**argv) {
    // program.bin policy trace delay-ms queue-phase missed-move replay bankA bankB per-player-difficulty
    if(argc!=11)return 2;
    unsigned delay=unsigned(strtoul(argv[4],nullptr,10));
    unsigned phase=unsigned(strtoul(argv[5],nullptr,10));
    unsigned miss=unsigned(strtoul(argv[6],nullptr,10));
    bool replay=atoi(argv[7])!=0;
    if(phase>16 || delay>30000)return 2;
    for(unsigned bank=0;bank<2;bank++) {
        unsigned value=unsigned(strtoul(argv[8+bank],nullptr,10));
        if(value>255)return 2;
        machine.m_banks[2+bank]=uint8_t(value);
    }
    unsigned difficulty=(~machine.m_banks[2]&255)>>6;
    bool per_player_difficulty=atoi(argv[10])!=0;
    std::vector<ArcadeEuroRule> rules;
    std::vector<uint16_t> order;
    FILE *policy=fopen(argv[2],"r");
    if(!policy)return 3;
    char header[128];
    if(!fgets(header,sizeof header,policy)||strcmp(header,"HYPCADE_EURO_POLICY_V1\n"))return 3;
    unsigned id,control,target,rank;
    while(fscanf(policy,"%u %u %u %u",&id,&control,&target,&rank)==4) {
        if(id>704 || target>65535 || control>16 || rules.size()>=65535)return 3;
        order.push_back(uint16_t(rules.size()));
        rules.push_back({uint16_t(id),uint16_t(target),uint8_t(control)});
    }
    fclose(policy);
    FILE *rom=fopen(argv[1],"rb");
    if(!rom||fread(machine.m_cpumem,1,32768,rom)!=32768)return 3;
    fclose(rom);
    std::vector<Input> inputs;
    FILE *trace=fopen(argv[3],replay?"r":"w");
    if(!trace)return 3;
    if(replay) {
        unsigned long long cycle;unsigned action,down;
        while(fscanf(trace,"%llu %u %u",&cycle,&action,&down)==3) {
            if(action>13 || down>1 || (!inputs.empty()&&cycle<inputs.back().cycle))return 3;
            inputs.push_back({cycle,action,down});
        }
        fclose(trace);trace=nullptr;
    }
    auto send=[&](unsigned action,bool down) {
        if(trace)fprintf(trace,"%llu %u %u\n",(unsigned long long)now_cycles,action,unsigned(down));
        if(down)machine.input_enable(action,0);else machine.input_disable(action,0);
    };
    auto word=[](unsigned at){return unsigned(machine.m_cpumem[at])|(unsigned(machine.m_cpumem[at+1])<<8);};
    auto score=[](){unsigned n=0;for(unsigned i=0;i<3;i++){unsigned v=machine.m_cpumem[0xa142+i];n=n*100+(v>>4)*10+(v&15);}return n;};
    for(unsigned c=0;c<4;c++)irq_next[c]=1e30;
    ctc_init(1000.0/3579545,0,0,2000.0/3579545,0);
    Z80Bus bus{&machine,mem_read,mem_write,port_read,port_write};z80_init(&machine.z80,bus);
    uint64_t next_nmi=0,release=0,last_window=0;
    ArcadeMoveSelection selected{},pending{};
    unsigned initial_lives=0,moves=0,offered=0,ending_at=0,peak_score=0;
    unsigned held=0,poll=0,delivery=0,queued=0,last_record=0;
    bool coin=false,start=false,won=false,previous_ready=false,skipped=false;
    size_t replay_at=0;
    while(now_cycles<3600ULL*3579545) {
        unsigned ms=now_cycles*1000/3579545;
        if(replay) {
            while(replay_at<inputs.size()&&now_cycles>=inputs[replay_at].cycle) {
                const auto &in=inputs[replay_at++];send(in.action,in.down);
                if(in.down&&in.action<5)++moves;
            }
        } else {
            bool newcoin=ms>=60000+delay&&ms<64000+delay&&(ms-delay)%1000<100;
            bool newstart=ms>=65000+delay&&ms<70000+delay&&(ms-delay)%1000<200;
            if(coin!=newcoin){send(SWITCH_COIN1,newcoin);coin=newcoin;}
            if(start!=newstart){send(SWITCH_START1,newstart);start=newstart;}
            // Model 8 ms Java polling and 17 ms SDL delivery, using only the
            // shared packaged selector published at the driver's 50 Hz tick.
            if(ms>=poll) {
                poll=ms+8;
                if(held&&now_cycles>=release){send(__builtin_ctz(held),false);held=0;}
                if(!held&&pending.ready) {
                    if(selected.ready&&selected.window==pending.window) {
                        ++offered;
                        if(miss&&offered==miss)skipped=true;
                        else {queued=pending.controls;delivery=ms+(phase+17-ms%17)%17;}
                    }
                    pending={};
                }
            }
            if(queued&&ms>=delivery) {
                held=queued;queued=0;send(__builtin_ctz(held),true);
                release=now_cycles+3579545/10;++moves;
            }
        }
        unsigned record=word(0xa17a),life=machine.m_cpumem[0xa149],flags=machine.m_cpumem[0xa111];
        if(ms>65000+delay&&life>0&&life<=9&&!initial_lives)initial_lives=life;
        if(initial_lives&&!won&&machine.m_cpumem[0xa18e]!=difficulty) {
            printf("{\"win\":false,\"difficulty_mismatch\":%u,\"expected\":%u}\n",machine.m_cpumem[0xa18e],difficulty);
            if(trace)fclose(trace);
            return 8;
        }
        if(initial_lives && record!=last_record && record<=704) {
            last_record=record;
            fprintf(stderr,"STEP time=%u record=%u frame=%d score=%u lives=%u\n",ms,record,player.get_current_frame(),score(),life);
        }
        if(initial_lives&&!won&&record>704) {
            printf("{\"win\":false,\"invalid_record\":%u,\"moves\":%u,\"score\":%u,\"lives\":%u,\"ms\":%u}\n",record,moves,score(),life,ms);
            if(trace)fclose(trace);
            return 7;
        }
        if(initial_lives&&(flags&64)&&life>0&&record>0&&record<=704&&!won) {
            const unsigned address=0x2088+(record-1)*32;
            const unsigned first=word(address),frame=player.get_current_frame();
            if((machine.m_cpumem[address+2]&64)&&word(0xa10f)==first&&
                player.get_status()==PLAYER_PLAYING&&frame>=first&&frame<=first+machine.m_cpumem[address+3]+1) {
                won=true;ending_at=ms;
            }
        }
        if(won) {
            peak_score=max(peak_score,score());
            if(ms>ending_at+9000) {
                bool valid=(!miss || (skipped||replay)) && life==initial_lives-(miss?1:0);
                printf("{\"win\":%s,\"score\":%u,\"moves\":%u,\"lives\":%u,\"initial_lives\":%u,\"ms\":%u,\"difficulty\":%u,\"replay\":%s}\n",valid?"true":"false",peak_score,moves,life,initial_lives,ms,difficulty,replay?"true":"false");
                if(trace)fclose(trace);
                return valid?0:5;
            }
        }
        if(initial_lives&&!won&&((life<initial_lives-(miss?1:0)) || (!miss&&(flags&16)))) {
            printf("{\"win\":false,\"record\":%u,\"frame\":%d,\"moves\":%u,\"score\":%u,\"lives\":%u,\"ms\":%u}\n",record,player.get_current_frame(),moves,score(),life,ms);
            if(trace)fclose(trace);
            return 5;
        }
        for(unsigned c=0;c<4;c++)if(now_cycles>=irq_next[c]){irq_next[c]+=irq_period[c];machine.do_irq(c);}
        if(now_cycles>=next_nmi) {
            next_nmi+=3579545/50;machine.do_nmi();
            selected=initial_lives&&player.get_status()==PLAYER_PLAYING ?
                arcade_select_euro_move(rules.data(),order.data(),order.size(),machine.m_cpumem,sizeof machine.m_cpumem,player.get_current_frame(),per_player_difficulty):ArcadeMoveSelection{};
            if(selected.ready&&(!previous_ready||last_window!=selected.window))pending=selected;
            if(!selected.ready)pending={};
            previous_ready=selected.ready;last_window=selected.window;
        }
        now_cycles+=z80_step(&machine.z80);
        if(machine.z80.irq_taken){machine.z80.irq=false;machine.z80.irq_taken=false;}
    }
    if(trace)fclose(trace);
    puts("{\"win\":false,\"timeout\":true}");return 6;
}
