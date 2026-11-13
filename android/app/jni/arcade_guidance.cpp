/* Hypcade adaptation/modification notice (2026-11-08).
 * Original authors and component licenses are retained; see MODIFICATIONS.md. */
// SPDX-License-Identifier: GPL-3.0-or-later
// RAM layout knowledge adapted from Jeff Nyman's laser-vault (GPL-3.0),
// commit 1f12c84dfabf3c8e5d028c8804b2f96678c798fa. See Android notices.
#include "arcade_guidance.h"
#include "arcade_signature.h"
#include <atomic>
#include <cstring>
#ifndef HYPSEUS_GUIDANCE_HOST_TEST
#include <jni.h>
#endif

#include "arcade_moves.inc"

static std::atomic<int> selected_move_policy{1};
void arcade_set_move_policy(int mode) {
    selected_move_policy.store(mode==2 ? 2 : 1,std::memory_order_relaxed);
}
ArcadeMove arcade_decode_cine(const uint8_t *memory, size_t size, bool ace, unsigned frame) {
    ArcadeMove result;
    if(size<0xa1e0)return result;
    bool fewest=selected_move_policy.load(std::memory_order_relaxed)==2;
    const ArcadeRomMove *entries=ace ? (fewest ? ace_moves_fewest : ace_moves_max)
                                     : (fewest ? dle21_moves_fewest : dle21_moves_max);
    size_t count=ace ? (fewest ? sizeof(ace_moves_fewest)/sizeof(*ace_moves_fewest) : sizeof(ace_moves_max)/sizeof(*ace_moves_max))
                     : (fewest ? sizeof(dle21_moves_fewest)/sizeof(*dle21_moves_fewest) : sizeof(dle21_moves_max)/sizeof(*dle21_moves_max));
    auto selected=arcade_select_rom_move(entries,count,memory+0xa000,frame,ace);
    result.controls=selected.controls;result.ready=selected.ready;result.window=selected.window;
    return result;
}

ArcadeMove arcade_decode_dl2(const uint8_t *memory, size_t size) {
    ArcadeMove result;
    if (size < 0x20000) return result;
    auto word = [memory](unsigned offset) { return unsigned(memory[0x10000 + offset]) |
        (unsigned(memory[0x10000 + offset + 1]) << 8); };
    // US 3.19 ROM 2780/2790 enters two accepting phases: A160 starts the
    // first; A15C starts the later cue phase. ROM 287c closes at A15A
    // (exclusive). Waiting for A15C can leave only one video frame.
    unsigned frame = word(0xa158), opens = word(0xa160), closes = word(0xa15a);
    if (!opens || closes <= opens || frame >= closes || frame + 12 < opens) return result;
    unsigned scene = word(0x56aa) & 63;
    unsigned record = word(0x5694 + 2 * scene);
    unsigned address = 0x5a24 + 14 * record;
    if (address + 14 > 0x10000) return result;
    const uint8_t *rec = memory + 0x10000 + address;
    // US 3.19 dispatches input records 0/1 and 4/5 through the same move
    // handler (ROM 1c20). Bit 2 marks a special/exit move, not a death clip.
    if ((rec[0] != 0 && rec[0] != 1 && rec[0] != 4 && rec[0] != 5) ||
        frame < unsigned(rec[2] | (rec[3] << 8))) return result;
    switch (rec[1]) {
        case 1: result.controls = 1; break;
        case 3: result.controls = 8; break;
        case 5: result.controls = 2; break;
        case 7: result.controls = 4; break;
        case 10: result.controls = 16; break;
        default: return result;
    }
    result.ready = frame >= opens;
    result.window = (uint64_t(record) << 32) | (uint64_t(opens) << 16) | closes;
    return result;
}

static std::atomic<bool> enabled{false};
static std::atomic<bool> visual_enabled{false};
static std::atomic<bool> watch_mode_enabled{false};
static std::atomic<bool> watch_automation_active{false};
static std::atomic<uint64_t> pending_watch_event{0};
static std::atomic<int> watch_credit_count{-1};
static std::atomic<bool> watch_coin_pending{false};
static std::atomic<bool> watch_game_started{false};
bool arcade_visual_moves_enabled() { return visual_enabled.load(std::memory_order_relaxed); }
bool arcade_watch_mode_enabled() { return watch_mode_enabled.load(std::memory_order_relaxed); }
void arcade_watch_publish_credits(int credits) {
    watch_credit_count.store(credits >= 0 && credits <= 99 ? credits : -1,
                             std::memory_order_release);
}
void arcade_watch_publish_coin_pending(bool pending) {
    watch_coin_pending.store(pending, std::memory_order_release);
}
void arcade_watch_publish_game_started(bool started) {
    watch_game_started.store(started, std::memory_order_release);
}
static std::atomic<uint64_t> published{0};
unsigned arcade_visual_controls() {
    return arcade_visual_moves_enabled() ? unsigned(published.load(std::memory_order_relaxed)) & 31 : 0;
}
bool arcade_guidance_enabled() { return enabled.load(std::memory_order_relaxed); }
// These fields are accessed only by the emulation thread.
static uint64_t previous_window = 0;
static bool previous_ready = false;
static uint32_t sequence = 0;
static void publish(ArcadeMove move) {
    bool new_move = move.ready && (!previous_ready || previous_window != move.window);
    if (new_move) ++sequence;
    previous_ready = move.ready;
    previous_window = move.window;
    // Publish readiness before exposing the event to the Android input thread.
    // Otherwise it can consume the event while still seeing the previous state.
    published.store((uint64_t(sequence) << 32) | (move.ready ? 256 : 0) | move.controls,
                    std::memory_order_release);
    if (!move.ready) pending_watch_event.store(0, std::memory_order_release);
    else if (new_move && watch_automation_active.load(std::memory_order_relaxed))
        pending_watch_event.store((uint64_t(sequence) << 32) | move.controls,
                                  std::memory_order_release);
}

void arcade_guidance_cine(const uint8_t *memory, size_t size, const char *game, bool playing, unsigned frame) {
    if (!enabled.load(std::memory_order_relaxed)) return;
    bool ace = std::strcmp(game, "ace") == 0;
    publish(playing && (ace || std::strcmp(game, "dle21") == 0)
        ? arcade_decode_cine(memory, size, ace, frame) : ArcadeMove{});
}
void arcade_guidance_dl2(const uint8_t *memory, size_t size, bool supported, bool playing) {
    if (!enabled.load(std::memory_order_relaxed)) return;
    publish(playing && supported ? arcade_decode_dl2(memory, size) : ArcadeMove{});
}
void arcade_configure_guidance(int mode, bool cue, bool watch) {
    bool visual=mode==1 || mode==2;
    arcade_set_move_policy(mode);
    visual_enabled.store(visual, std::memory_order_relaxed);
    watch_mode_enabled.store(watch, std::memory_order_relaxed);
    watch_automation_active.store(false, std::memory_order_relaxed);
    pending_watch_event.store(0, std::memory_order_relaxed);
    watch_credit_count.store(-1, std::memory_order_relaxed);
    watch_coin_pending.store(false, std::memory_order_relaxed);
    watch_game_started.store(false, std::memory_order_relaxed);
    enabled.store(visual || cue || watch, std::memory_order_relaxed);
}
bool arcade_hide_dl2_move_text(const char *game, unsigned x, unsigned y, unsigned line) {
    return game && std::strcmp(game,"lair2")==0 && x==32 && y==47 && line==2 &&
        arcade_watch_mode_enabled() && !arcade_visual_moves_enabled();
}
uint64_t arcade_guidance_snapshot() {
    return published.load(std::memory_order_acquire);
}
void arcade_set_watch_automation(bool active) {
    if (!active) {
        watch_automation_active.store(false, std::memory_order_release);
        pending_watch_event.store(0, std::memory_order_release);
        return;
    }
    pending_watch_event.store(0, std::memory_order_relaxed);
    watch_automation_active.store(true, std::memory_order_release);
}
void arcade_request_current_watch_move() {
    uint64_t state = published.load(std::memory_order_acquire);
    if ((state & UINT64_C(256)) && (state & UINT64_C(31))) {
        uint64_t expected = 0;
        pending_watch_event.compare_exchange_strong(expected,
            (state & UINT64_C(0xffffffff00000000)) | (state & 31),
            std::memory_order_release, std::memory_order_relaxed);
    }
}
uint64_t arcade_take_watch_move() {
    uint64_t event = pending_watch_event.exchange(0, std::memory_order_acq_rel);
    uint64_t current = published.load(std::memory_order_acquire);
    if (!(current & 256) || (current >> 32) != (event >> 32) || (current & 31) != (event & 31)) return 0;
    return event;
}
#ifndef HYPSEUS_GUIDANCE_HOST_TEST
extern "C" JNIEXPORT void JNICALL
Java_org_hypseus_android_HypseusActivity_nativeEnableGuidance(JNIEnv *, jclass, jint mode,
                                                              jboolean cue, jboolean watch) {
    arcade_configure_guidance(mode, cue, watch);
}
extern "C" JNIEXPORT jint JNICALL
Java_org_hypseus_android_HypseusActivity_nativeWatchCredits(JNIEnv *, jclass) {
    return watch_credit_count.load(std::memory_order_acquire);
}
extern "C" JNIEXPORT jboolean JNICALL
Java_org_hypseus_android_HypseusActivity_nativeWatchCoinPending(JNIEnv *, jclass) {
    return watch_coin_pending.load(std::memory_order_acquire) ? JNI_TRUE : JNI_FALSE;
}
extern "C" JNIEXPORT jboolean JNICALL
Java_org_hypseus_android_HypseusActivity_nativeWatchGameStarted(JNIEnv *, jclass) {
    return watch_game_started.load(std::memory_order_acquire) ? JNI_TRUE : JNI_FALSE;
}
extern "C" JNIEXPORT jlong JNICALL
Java_org_hypseus_android_HypseusActivity_nativeGuidance(JNIEnv *, jclass) {
    return static_cast<jlong>(arcade_guidance_snapshot());
}
extern "C" JNIEXPORT void JNICALL
Java_org_hypseus_android_HypseusActivity_nativeSetWatchAutomation(JNIEnv *, jclass, jboolean active) {
    arcade_set_watch_automation(active);
}
extern "C" JNIEXPORT void JNICALL
Java_org_hypseus_android_HypseusActivity_nativeRequestCurrentWatchMove(JNIEnv *, jclass) {
    arcade_request_current_watch_move();
}
extern "C" JNIEXPORT jlong JNICALL
Java_org_hypseus_android_HypseusActivity_nativeTakeWatchMove(JNIEnv *, jclass) {
    return static_cast<jlong>(arcade_take_watch_move());
}
#endif

void arcade_configure_dl2_moves(uint8_t *memory, size_t size, bool visual) {
    if (!memory || size <= 0xf2805) return;
    memory[0xf2804] = visual ? 0x90 : 0xeb;
    memory[0xf2805] = visual ? 0x90 : 0x4a;
}
