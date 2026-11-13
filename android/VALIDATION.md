# Validation

This document summarizes the checked implementation and its limits. Detailed
results and source fingerprints live in
[the verification reports](moves/rom-tables/verification/).
[BUILD-PROVENANCE.json](BUILD-PROVENANCE.json) records the signed release APK
hashes, toolchain and build checks.

## Android video backend

`video_android.cpp` is compiled only for Android. Host checks exercise its retained
ROM text and recorded moves, CRT target reuse and disabling, texture retirement,
renderer cleanup and mobile resizing. The shared source also passes a desktop
syntax check; a complete desktop build was not performed.

Release packaging checks verify that the unused embedded desktop icon and splash
artwork are absent from the native libraries, and that the removed decoder-toggle
label is absent from the APK. Decoding remains automatic with software fallback.
The Android launcher check confirms the toggle is absent. Compared with the
pre-refactor signed 0.1 binaries, the combined desktop-code exclusion, backend
extraction and toggle removal save about 57 KiB per ARM APK and 260 KiB per
uncompressed native library. Exact sizes are recorded in build provenance.

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

The following batches passed on both the laptop and an Android 9 / API 28 x86
emulator. Counts are **per backend**.

| Check | Cases | What passed |
| --- | ---: | --- |
| ROM policies and independent replays | 208 | Both objectives, eight starts for DLE21 and every combination of Space Ace's three skills and four operator difficulties; complete games without life loss |
| Packaged Watch Mode lookup | 234 | Off using Max score, Max score and Fewest moves; two independent starts and input-queue phases of 0, 8 and 16 ms; packaged rows only, with no learning or fallback |
| Space Ace branch detours | 72 | Both strategies, three separately introduced detours, all three skills and all four operator difficulties; selected-strategy guidance resumes and the game finishes without life loss |
| DL2 production-player harness | 45 | All five difficulties, seek delays of 0, 17 and 55 ms, and queue phases of 0, 8 and 16 ms; complete games without life loss |

Host and Android produced identical policy traces, Watch Mode results and DL2
final states. Repeated starts produced seven or eight distinct scene/action
sequences for each policy configuration, confirming that the tests sampled
different natural routes.

The DL2 harness runs the production Java Watch Mode controller and JNI guidance
with Hypseus's i86 CPU, Sony protocol and extracted driver methods. Withholding
the first or final move caused a detected death on both backends. Those negative
controls check that the harness can distinguish a failed play from a win.

Runtime rows are generated directly from the independent ROM-policy replays.
The complete extraction command emits one merged JSON file per game, containing
its shared rows and both strategy index lists, plus the generated APK include.
A fresh 208-case host extraction and independent-replay run reproduced the
APK's move include byte for byte. Bundle checks also verify direct generation
in place and rejection of incomplete verification reports.
The direct tables are checked across the same skill, difficulty and timing
matrix before packaging.
The current shared lookup passed all 234 host and Android cases with unchanged
scores. Both strategies cover the union of verified branch contexts, while
their ROM policies retain the choice to wait instead of taking an optional
action. Each detour test follows the other strategy at one decision, then
returns to the selected strategy. All 72 detours were actually exercised on
each backend. Host and Android results matched for all 306 cases per backend.

Unique move rows are stored once per game, with separate 16-bit strategy index
lists. Expanding those lists reproduces all 9,293 logical rows in the same
priority order. A host differential check matched the previous selector in
1,003,644 timing-boundary cases. Checks cover index bounds, sorted lookup order, complete pool use and the presence of pools
and index lists in all four signed release APKs.

Space Ace's necessary final UP remains in both policies even though it awards
no points. Bundled-data checks verify that action, the complete replay evidence,
the separate policy arrays and their presence in all four release APKs.

For reproduction, follow the [offline tool guide](../tools/offline-moves/README.md)
and [Watch Mode verification guide](../tools/offline-moves/WATCH-VERIFY.md).
These simulations omit video and real-time waits. Running them on Android
checks the native/JVM backend; it does not exercise an APK's full media pipeline.
The actual APK gameplay runs listed below predate the shared-table build; no
new full gameplay run through the launcher was performed for this change.

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

- The existing Hypcade release certificate, version 0.1, minimum SDK 25 and
  target SDK 36.
- One ABI per flavor and the expected bundled move data.
- Fixed arcade landscape and absence of touch-control code; mobile controls
  and orientation policy remain present.
- ARM release lint: zero errors, with 43 arcade warnings and 38 mobile warnings.

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
