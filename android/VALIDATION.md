# Validation

This document summarizes the checked implementation and its limits. Detailed
results and source fingerprints live in
[the verification reports](moves/rom-tables/verification/).
Signed APK checksums accompany the release files; toolchain versions and build
commands are documented in the [Android guide](README.md).

## Android video backend

`video_android.cpp` is compiled only for Android. Host checks exercise its retained
ROM text and recorded moves, CRT target reuse and disabling, texture retirement,
renderer cleanup and mobile resizing. The shared source also passes a desktop
syntax check; a complete desktop build was not performed.

Release packaging checks verify that the unused embedded desktop icon and splash
artwork are absent from the native libraries, and that the removed decoder-toggle
label is absent from the APK. Decoding remains automatic with software fallback.
The Android launcher check confirms the toggle is absent. Compared with the
pre-refactor signed binaries, the combined desktop-code exclusion, backend
extraction and toggle removal save about 57 KiB per ARM APK and 260 KiB per
uncompressed native library.

## CRT video and text

The production game-layer GLES2 shader passes host GPU checks against an
independent pixel reference. The fixture includes YUV video, transparent glyphs,
native game text, RGBA/BGRA overlays, alpha modulation, clipping and rotation.
Added FPS and score/lives glyphs are then checked for unchanged white pixels.
The shared LDP1450 GPU function is also compared with the original bitmap
blitter using the actual font, including directions, button text, digits,
the special glyph, spaces, clipping, replacement and cached redraws. The same
font checks run with the software renderer. A focused host DL2 Watch replay
(Easy, 17 ms seek delay, 8 ms input phase) completed with all 302 moves and no
life loss after replacing the text-submission path.
Repeated frames check SDL state restoration; unsupported renderers and invalid
frame sizes exercise the fallback. Run
`python3 android/tests/test_crt_shader.py --native` with an existing shared
SDL3/GLES2 installation and Mesa EGL to reproduce these checks.

The signed Android 9 x86 release APK also passed checks through the normal
launcher, using original synthetic Singe overlays and flat gray MPEG-2 video.
Native 1280x960 captures check filtered game-overlay text and unfiltered FPS text,
identical scanline spacing for 640x480 and 1440x1080 sources, and plain software
fallback. Video row contrast was 25.5 levels and mask contrast was 8.5 levels.
A short DL2 US 3.19 session through the launcher also displayed native ROM text
using the shared cached-font renderer, with scanlines visible on its glyphs and
the added scoreboard/FPS drawn afterward. This checks rendering, not a complete
commercial-game playthrough. The emulator's settings were restored after testing.

CRT-on rendering reuses an output-sized GPU buffer for video, ROM game text and
recorded moves. Added score/lives overlays, FPS, subtitles and bezels are drawn
afterward without filtering. CRT-off rendering retains the direct path.
These checks do not measure Yoga Flame performance or replace commercial-game testing.

## Move policies and Watch Mode

Bundled coverage is checked independently of successful games. Reconstructing
the full inventory from the supplied ROM ZIPs accounts for all 3,681 DLE21 and
10,267 Space Ace A3 rules. Every ranked alternative is represented in both
runtime policies where applicable: 1,178 DLE21 and 1,132 Space Ace choices before
pool deduplication. Death, ignored, empty and dispatch windows remain auditable.
Equivalent diagonals have supported single-control outcomes; an unranked rule
with a safe structural continuation fails packaging. Tests deliberately remove
a rule or policy alternative and require rejection.

The complete-policy selector passed these new video-less checks:

| Check | Host | Android 9 x86 | What passed |
| --- | ---: | ---: | --- |
| Normal packaged Watch Mode | 104 | 39 | All supported configurations; host uses both strategies, two starts and queue phases 0/16 ms; Android uses Off/Max score/Fewest moves at 8 ms |
| Deliberate life loss and recovery | 39 | 26 | Withhold move 20 until death, resume with bundled data only, and complete without another loss; host includes Off, Android checks both visible strategies |
| DL2 production-player harness | 5 | 5 | All five difficulties, 17 ms seek delay and 8 ms queue phase; complete games without life loss |
| DL2 omitted-input controls | 2 | 2 | Withholding the first or final move causes a detected death |

The 26 common retry results match exactly between host and Android, including
score, move count and the single intended life loss. Focused DL1 diagnostics
also recovered after omissions at moves 1, 5, 10, 15, 20, 25, 30, 35 and 40.
Before the fix, several of those tests lost a second life because retry-only
steps had no packaged rows. The failure occurs without video; it is not caused
by HD media resolution.

Successful sampled routes remain as timing calibration evidence, separate from
the complete ROM policy. The archived 208-case policy/replay matrices and older
Watch/actual-APK reports describe the earlier sampled selector; they are not
new tests of this implementation. New reports under `verification/complete-*`
record the current selector source fingerprints. Space Ace's necessary
zero-score final UP remains covered, and DL2 continues to read its live ROM
prompts rather than a sampled move export.

All four signed releases are cross-built and checked for the native rule pools
and strategy indices, signature, ABI and SDK declarations. These headless
checks do not establish every possible input timing, random sequence, global
optimality, or commercial-game performance on the cabinet.

For reproduction, follow the [offline tool guide](../tools/offline-moves/README.md)
and [Watch Mode verification guide](../tools/offline-moves/WATCH-VERIFY.md).
These simulations omit video and real-time waits. Running them on Android
checks the native/JVM backend; it does not exercise an APK's full media pipeline.
The actual APK gameplay runs listed below predate the complete-policy build;
no new full gameplay run through the launcher was performed for this change.

## Move text and audio cues

The production-renderer regression compares DL2's native SWORD text with and
without a simultaneously published BUTTON action: the images must be identical.
Clearing the native prompt must leave no calculated replacement. The same test
checks calculated text for DLE21 and Space Ace, and native-only text for Space
Ace '91, including renderer teardown and reinitialization. It fails before the
duplicate-text fix and passes afterward on GLES2 and software rendering.

DL1 and Space Ace calculated text is visible only while the shared native move
state is ready. Audio observes the same event sequence. Host tests verify that
previews produce neither text nor a beep, readiness exposes the action, repeated
polls do not repeat a beep, and stopping cancels audio polling. The ROM lookup
and Watch Mode timing are unchanged.

DL2 US 3.19 has separate operator-difficulty and per-scene prompt gates. Android
now bypasses both when Show moves is enabled; disabling moves restores the
difficulty branch and skips the prompt path. The video-less harness calls that
production configuration rather than applying a partial copy of the patch.
With `--check-prompts`, all 45 combinations of five difficulties, three seek
delays and three input-queue phases pass on both the host and Android 9 x86.
Each completed game emits all 302 native text prompts, with none appearing
before its acceptance window or at/after its closing boundary. All games finish
without a lost life; host and Android results match exactly. First/final input
omission controls still detect death on both backends.

The signed release flavors are rebuilt and inspected separately. These checks
measure ROM text generation and software event timing, not physical screen or
audio latency. The renderer presents text on its next frame, and the Java audio
callback polls every 16 ms before Android's device-dependent output delay. No
new full commercial-game run through the APK launcher or on the cabinet was
performed for this cue-alignment change.

## Direct APK gameplay

Separate runs went through the launcher on the Android 9 x86 emulator at
960×720, using an isolated debug application with the production native code.
Read-only memory inspection observed game state; the tests did not inject seeks
or write game memory.

| Game | Configuration | Result | Media |
| --- | --- | --- | --- |
| DLE21 | Fewest moves | Ending reached, 314,457 points, all five starting lives retained | Original game media |
| Space Ace A3 | Fewest moves, Captain skill, after 5 episodes / fast | Ending reached, 213,098 points, all five starting lives retained | Synthetic MPEG-2 disc timing |
| DL2 US 3.19 | Hardest difficulty | Ending reached with all three starting lives retained | Synthetic black MPEG-2 with original disc timing |

The DL2 memory trace covers the ending portion; its Java input log covers the
session. Its direct-run evidence establishes an ending with the starting lives
retained, while the full video-less harness checks life loss throughout play.

The DL2 failure investigation showed that inputs reached the board after the
acceptance window. The decoder had used a later cue threshold as its opening
and excluded valid special/exit input records. The corrected decoder uses the
ROM's earliest accepted phase and exclusive closing frame. No new Hypseus CPU
or game-driver changes were needed for this correction.

## Build and packaging

All four signed release flavors assembled successfully: ARMv7 arcade, ARM64
mobile, x86 arcade emulator and x86_64 mobile emulator. Checks verified:

- The existing Hypcade release certificate, version v0.2.1, minimum SDK 25 and
  target SDK 36.
- One ABI per flavor and the expected bundled move data.
- Fixed arcade landscape and absence of touch-control code; mobile controls
  and orientation policy remain present.
- Previous ARM release lint: zero errors, with 43 arcade warnings and 38 mobile
  warnings; not rerun for the renderer-only duplicate-text fix.

Focused checks also passed for ROM-table export, causal score/progression and
death detection, guidance boundaries, Watch Mode lifecycle and stale events,
launcher/controller logic, and pinned dependencies. Build diagnostics include
existing native compiler warnings, an SDK XML version warning, 32-bit flavor
warnings and Gradle deprecations. These are not warning-free builds.

## What remains unproven

Finite randomized starts do not prove every retry state, later round, reachable
branch or globally optimal strategy. Exporting every decoded ROM window does
not establish that every such window is reachable or executable by the player.

Synthetic timing media exercises ROM control flow, frame advancement and seeks;
it cannot establish commercial video accuracy or audible synchronization.
The direct gameplay runs used a debug APK; the matching release sources were
cross-built and their signed packages checked separately.

These single-player checks do not establish two-player behavior, every live
scoreboard counter, all storage/lifecycle scenarios, or performance on every
Android device. A synthetic playback fixture's `ANDROID_MEDIA_TEST PASS` marker
only confirms frame advancement; it is not a commercial-game accuracy test.
