/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
// SPDX-License-Identifier: GPL-3.0-or-later
// Original Euro CPU/driver/VP932 methods plus production JNI guidance and Java.
#include <jni.h>
#include <deque>
#include <cassert>
#include "../../android/app/jni/arcade_guidance.h"
#include "euro_machine.inc"

struct QueuedInput { unsigned action; bool down; uint64_t at; };
static std::deque<QueuedInput> inputs, coins;
static uint64_t elapsed_ms, next_nmi, last_coin;
static unsigned input_phase, initial_lives, moves_count, starts_count, coin_count;
static unsigned started_at, ending_at, peak_score;
static bool started, finished, failed, startup_only;
extern "C" jint Java_org_hypseus_android_HypseusActivity_nativeWatchCredits(JNIEnv*,jclass);
extern "C" jboolean Java_org_hypseus_android_HypseusActivity_nativeWatchGameStarted(JNIEnv*,jclass);
static void check_boot_publication(int mode) {
    // Exercise all uniform RAM-test patterns against the actual JNI publisher.
    // The lower 32 KiB ROM remains untouched; reset the scratch RAM afterward.
    for(unsigned pattern=0;pattern<256;pattern++) {
        std::fill(machine.m_cpumem+0xa000,machine.m_cpumem+0xa800,uint8_t(pattern));
        arcade_configure_guidance(mode,false,true);
        arcade_guidance_euro(machine.m_cpumem,sizeof machine.m_cpumem,machine.m_shortgamename,true,6000);
        assert(Java_org_hypseus_android_HypseusActivity_nativeWatchCredits(nullptr,nullptr)==-1);
        assert(!Java_org_hypseus_android_HypseusActivity_nativeWatchGameStarted(nullptr,nullptr));
    }
    auto *ram=machine.m_cpumem;
    std::fill(ram+0xa000,ram+0xa800,0);
    ram[0xa102]=0xfb;ram[0xa103]=0xed;ram[0xa104]=0x4d;
    ram[0xa14b]=0x42;ram[0xa149]=3;ram[0xa17a]=6;ram[0xa001]=1;
    arcade_guidance_euro(ram,sizeof machine.m_cpumem,machine.m_shortgamename,true,6000);
    assert(Java_org_hypseus_android_HypseusActivity_nativeWatchCredits(nullptr,nullptr)==42);
    assert(!Java_org_hypseus_android_HypseusActivity_nativeWatchGameStarted(nullptr,nullptr));
    ram[0xa001]=0;
    arcade_guidance_euro(ram,sizeof machine.m_cpumem,machine.m_shortgamename,true,6000);
    assert(Java_org_hypseus_android_HypseusActivity_nativeWatchGameStarted(nullptr,nullptr));
    std::fill(ram+0xa000,ram+0xa800,0);
}
static unsigned word(unsigned at) { return machine.m_cpumem[at] | (machine.m_cpumem[at+1]<<8); }
static unsigned score() {
    unsigned result=0;
    for(unsigned i=0;i<3;i++){unsigned v=machine.m_cpumem[0xa142+i];result=result*100+(v>>4)*10+(v&15);}
    return result;
}
extern "C" JNIEXPORT jboolean JNICALL Java_org_hypseus_android_HypseusActivity_nativeEmulatorReady(JNIEnv*,jclass) { return elapsed_ms>=17; }
extern "C" JNIEXPORT void JNICALL Java_org_hypseus_android_HypseusActivity_nativeArcadeInput(JNIEnv*,jclass,jint action,jboolean down) {
    if(action<0 || action>12)return;
    inputs.push_back({unsigned(action),down!=0,0});
    if(getenv("HYPCADE_WATCH_TRACE"))fprintf(stderr,"INPUT ms=%llu action=%d down=%d credits=%u flags=%u record=%u\n",
        (unsigned long long)elapsed_ms,action,down,machine.m_cpumem[0xa14b],machine.m_cpumem[0xa001],word(0xa17a));
}
extern "C" JNIEXPORT jboolean JNICALL Java_org_hypseus_android_EuroWatchMachine_init(JNIEnv *env,jclass,jstring path,jboolean italian,jint level,jint mode,jint phase,jboolean startup) {
    const char *filename=env->GetStringUTFChars(path,nullptr);FILE *rom=fopen(filename,"rb");env->ReleaseStringUTFChars(path,filename);
    if(!rom)return false;bool ok=fread(machine.m_cpumem,1,32768,rom)==32768;fclose(rom);
    if(!ok || level<0 || level>3 || mode<1 || mode>2 || phase<0 || phase>16)return false;
    machine.m_shortgamename=italian?"lair_ita":"laireuro";
    check_boot_publication(mode);
    machine.m_banks[2]=((italian?0xdf:0x16)&0x3f)|((3-level)<<6);
    machine.m_banks[3]=italian?0xef:0xf6;
    input_phase=phase;startup_only=startup;
    for(unsigned c=0;c<4;c++)irq_next[c]=1e30;
    ctc_init(1000.0/3579545,0,0,2000.0/3579545,0);
    Z80Bus bus{&machine,mem_read,mem_write,port_read,port_write};z80_init(&machine.z80,bus);
    arcade_configure_guidance(mode,false,true);return true;
}
static void deliver(unsigned action,bool down) {
    if(down)machine.input_enable(action,0);else machine.input_disable(action,0);
    if(down && action==SWITCH_START1)++starts_count;
    if(down && action==SWITCH_COIN1)++coin_count;
    if(started && down && action<5)++moves_count;
}
extern "C" JNIEXPORT void JNICALL Java_org_hypseus_android_EuroWatchMachine_advanceTo(JNIEnv*,jclass,jlong target) {
    while(elapsed_ms<(uint64_t)target && !finished && !failed) {
        ++elapsed_ms;
        while(now_cycles<elapsed_ms*3579545/1000) {
            for(unsigned c=0;c<4;c++)if(now_cycles>=irq_next[c]){irq_next[c]+=irq_period[c];machine.do_irq(c);}
            if(now_cycles>=next_nmi){next_nmi+=3579545/50;machine.do_nmi();}
            now_cycles+=z80_step(&machine.z80);
            if(machine.z80.irq_taken){machine.z80.irq=false;machine.z80.irq_taken=false;}
        }
        // SDL's 17 ms queue cadence and the engine's 125 ms sticky coin queue.
        if((elapsed_ms+input_phase)%17==0) {
            while(!inputs.empty()) {
                auto in=inputs.front();inputs.pop_front();
                if(in.action==SWITCH_COIN1){last_coin=std::max(last_coin,now_cycles)+3579545/8;in.at=last_coin;coins.push_back(in);}
                else deliver(in.action,in.down);
            }
            if(!coins.empty() && now_cycles>coins.front().at){auto in=coins.front();coins.pop_front();deliver(in.action,in.down);}
        }
        unsigned life=machine.m_cpumem[0xa149],record=word(0xa17a);
        if(!started && starts_count && !(machine.m_cpumem[0xa001]&1) && life>0 && life<=9 && record>=6 && record<=704) {
            started=true;initial_lives=life;started_at=elapsed_ms;
        }
        if(started) {
            peak_score=std::max(peak_score,score());
            if(life<initial_lives || record>704)failed=true;
            unsigned address=0x2088+(record?record-1:0)*32;
            if(!failed && record && record<=704 && (machine.m_cpumem[0xa111]&64) &&
                (machine.m_cpumem[address+2]&64) && word(0xa10f)==word(address) &&
                player.get_status()==PLAYER_PLAYING && player.get_current_frame()>=int(word(address)) &&
                player.get_current_frame()<=int(word(address)+machine.m_cpumem[address+3]+1) && !ending_at)ending_at=elapsed_ms;
            if(!failed && ((startup_only && moves_count>=3 && peak_score>0) ||
                           (ending_at && elapsed_ms>ending_at+9000)))finished=true;
        }
    }
}
extern "C" JNIEXPORT jint JNICALL Java_org_hypseus_android_EuroWatchMachine_status(JNIEnv*,jclass) { return finished?1:failed?-1:0; }
extern "C" JNIEXPORT jstring JNICALL Java_org_hypseus_android_EuroWatchMachine_summary(JNIEnv *env,jclass) {
    char text[640];snprintf(text,sizeof text,
        "{\"complete\":%s,\"started\":%s,\"no_life_loss\":%s,\"coins\":%u,\"starts\":%u,\"started_at\":%u,\"moves\":%u,\"score\":%u,\"lives\":%u,\"milliseconds\":%llu,\"raw_credits\":%u,\"flags\":%u,\"record\":%u,\"pc\":%u,\"ram_entry\":%u,\"ram_target\":%u,\"irq_entry\":%u}",
        finished?"true":"false",started?"true":"false",failed?"false":"true",coin_count,starts_count,started_at,moves_count,peak_score,
        machine.m_cpumem[0xa149],(unsigned long long)elapsed_ms,machine.m_cpumem[0xa14b],machine.m_cpumem[0xa001],word(0xa17a),machine.z80.pc,
        machine.m_cpumem[0xa102],word(0xa103),word(0xa100));
    return env->NewStringUTF(text);
}
