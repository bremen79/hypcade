# Validation

This document summarizes the checked implementation and its limits. Detailed
results and source fingerprints live in
[the verification reports](moves/rom-tables/verification/).
[BUILD-PROVENANCE.json](BUILD-PROVENANCE.json) records the signed release APK
hashes, toolchain and build checks.

## Move policies and Watch Mode

The following batches passed on both the laptop and an Android 9 / API 28 x86
emulator. Counts are **per backend**.

| Check | Cases | What passed |
| --- | ---: | --- |
| ROM policies and independent replays | 208 | Both objectives, eight starts for DLE21 and every combination of Space Ace's three skills and four operator difficulties; complete games without life loss |
| Packaged Watch Mode lookup | 234 | Off using Max score, Max score and Fewest moves; two independent starts and input-queue phases of 0, 8 and 16 ms; packaged rows only, with no learning or fallback |
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
There is no separate Watch Mode training stage or generated training directory.
The direct tables are checked across the same skill, difficulty and timing
matrix before packaging.
The reduced lookup passed all 234 host and Android cases with unchanged scores.
The cleaned checker itself was checked across 234 host cases and 39 Android
cases covering every skill/difficulty/mode combination. The broader Android
lookup comparison used the earlier checker with learning disabled.

Space Ace's necessary final UP remains in both policies even though it awards
no points. Bundled-data checks verify that action, the complete replay evidence,
the separate policy arrays and their presence in all four release APKs.

For reproduction, follow the [offline tool guide](../tools/offline-moves/README.md)
and [Watch Mode verification guide](../tools/offline-moves/WATCH-VERIFY.md).
These simulations omit video and real-time waits. Running them on Android
checks the native/JVM backend; it does not exercise an APK's full media pipeline.

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

The DLE21 and DL2 full-game evidence predates removal of the redundant Space Ace
rows. Their move data or decoder behavior was unchanged by that cleanup. The
Space Ace direct run above uses the reduced tables.
