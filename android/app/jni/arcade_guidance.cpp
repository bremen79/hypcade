/* Hypcade adaptation/modification notice (2026-11-08).
 * Original authors and component licenses are retained; see MODIFICATIONS.md. */
// SPDX-License-Identifier: GPL-3.0-or-later
// RAM layout knowledge adapted from Jeff Nyman's laser-vault (GPL-3.0),
// commit 1f12c84dfabf3c8e5d028c8804b2f96678c798fa. See Android notices.
#include "arcade_guidance.h"
#include "arcade_signature.h"
#include <algorithm>
#include <atomic>
#include <cstring>
#ifndef HYPSEUS_GUIDANCE_HOST_TEST
#include <jni.h>
#endif

struct SafeOutcome { uint64_t headers; uint8_t outcome; unsigned frame; };
#include "arcade_moves.inc"

static bool known(uint64_t headers, uint8_t outcome, bool ace, unsigned frame, bool canonical) {
    const SafeOutcome *begin = canonical ? (ace ? ace_canonical_moves : dle21_canonical_moves)
                                         : (ace ? ace_moves : dle21_moves);
    size_t count = canonical ? (ace ? sizeof(ace_canonical_moves)/sizeof(*ace_canonical_moves)
                                    : sizeof(dle21_canonical_moves)/sizeof(*dle21_canonical_moves))
                            : (ace ? sizeof(ace_moves)/sizeof(*ace_moves) : sizeof(dle21_moves)/sizeof(*dle21_moves));
    const SafeOutcome *entry = std::lower_bound(begin, begin + count, headers,
        [](const SafeOutcome &item, uint64_t key) { return item.headers < key; });
    for (; entry != begin + count && entry->headers == headers; ++entry)
        if (entry->outcome == outcome && frame + 24 >= entry->frame && frame <= entry->frame + 24) return true;
    return false;
}

ArcadeMove arcade_decode_cine(const uint8_t *memory, size_t size, bool ace, unsigned frame) {
    ArcadeMove result;
    if (size < 0xa1e0) return result;
    uint64_t hash = UINT64_C(14695981039346656037);
    for (int e = 0; e < 16; ++e) {
        const uint8_t *x = memory + 0xa0e0 + e * 16;
        if (!(x[0] & 0x80)) break;
        for (int k = 0; k < 12; ++k) { hash ^= x[k]; hash *= UINT64_C(1099511628211); }
    }
    uint64_t canonical = arcade_cine_signature(memory + 0xa0e0, 256);
    unsigned earliest = 1000;
    for (int e = 0; e < 16; ++e) {
        const uint8_t *x = memory + 0xa0e0 + e * 16;
        if (!(x[0] & 0x80)) break;
        unsigned delay = x[12];
        for (unsigned w = 0; w < (x[1] & 3); ++w) {
            unsigned duration = x[13 + w];
            if (!duration) continue;
            uint8_t outcome = x[2 + ((x[1] >> (2 + 2*w)) & 3)];
            if (outcome != 0xff && delay <= 12 && delay < earliest && (known(canonical, outcome, ace, frame, true) || known(hash, outcome, ace, frame, false))) {
                result.controls = (x[0] & 15) ? (x[0] & 15) : 16;
                result.ready = delay == 0;
                result.window = canonical ^ (uint64_t(e + 1) << 40) ^ (uint64_t(w + 1) << 32);
                earliest = delay;
            }
            delay += duration;
        }
    }
    return result;
}

ArcadeMove arcade_decode_dl2(const uint8_t *memory, size_t size) {
    ArcadeMove result;
    if (size < 0x20000) return result;
    auto word = [memory](unsigned offset) { return unsigned(memory[0x10000 + offset]) |
        (unsigned(memory[0x10000 + offset + 1]) << 8); };
    unsigned frame = word(0xa158), opens = word(0xa15c), closes = word(0xa15a);
    if (!opens || closes < opens || frame > closes || frame + 12 < opens) return result;
    unsigned scene = word(0x56aa) & 63;
    unsigned record = word(0x5694 + 2 * scene);
    unsigned address = 0x5a24 + 14 * record;
    if (address + 14 > 0x10000) return result;
    const uint8_t *rec = memory + 0x10000 + address;
    if (rec[0] > 1 || frame < unsigned(rec[2] | (rec[3] << 8))) return result;
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
bool arcade_visual_hints_enabled() { return visual_enabled.load(std::memory_order_relaxed); }
static std::atomic<uint64_t> published{0};
unsigned arcade_visual_controls() {
    return arcade_visual_hints_enabled() ? unsigned(published.load(std::memory_order_relaxed)) & 31 : 0;
}
bool arcade_guidance_enabled() { return enabled.load(std::memory_order_relaxed); }
// These fields are accessed only by the emulation thread.
static uint64_t previous_window = 0;
static bool previous_ready = false;
static uint32_t sequence = 0;
static void publish(ArcadeMove move) {
    if (move.ready && (!previous_ready || previous_window != move.window)) ++sequence;
    previous_ready = move.ready;
    previous_window = move.window;
    published.store((uint64_t(sequence) << 32) | (move.ready ? 256 : 0) | move.controls,
                    std::memory_order_relaxed);
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
#ifndef HYPSEUS_GUIDANCE_HOST_TEST
extern "C" JNIEXPORT void JNICALL
Java_org_hypseus_android_HypseusActivity_nativeEnableGuidance(JNIEnv *, jclass, jboolean visual, jboolean cue) {
    visual_enabled.store(visual, std::memory_order_relaxed);
    enabled.store(visual || cue, std::memory_order_relaxed);
}
extern "C" JNIEXPORT jlong JNICALL
Java_org_hypseus_android_HypseusActivity_nativeGuidance(JNIEnv *, jclass) {
    return static_cast<jlong>(published.load(std::memory_order_relaxed));
}
#endif

void arcade_configure_dl2_hints(uint8_t *memory, size_t size, bool visual) {
    if (!memory || size <= 0xf2805) return;
    memory[0xf2804] = visual ? 0x90 : 0xeb;
    memory[0xf2805] = visual ? 0x90 : 0x4a;
}
