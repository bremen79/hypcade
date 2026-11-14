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

## Scoreboard layouts

Space Ace now offers Off, Left and Right; its dedicated skill panel moves to
the opposite edge. This extension was built without running tests or a device
check, as requested. The checks below describe the earlier DL1/DL2 work.

Launcher model checks cover Off, Left, Right and Top arguments for Dragon's
Lair I and II, including suppression of DL1's default overlay when Off is
selected. Host renderer checks cover edge placement at output widths of 960,
1280 and 1920 pixels, while preserving native positioning for other games.

Host GLES2 and software-renderer checks also exercise the production scoreboard
collection with two independent test painters. Both must complete before one
texture upload; a second call without a repaint must not upload. All three
layouts retain the same texture across changed and blanked digits, while pixel
checks verify transparent clearing and unchanged background video. These are
component rendering checks, not a new cabinet gameplay test; no ADB device was
connected for this refactor.

The signed ARMv7 arcade build was exercised through the launcher on the physical
Yoga Flame cabinet (Android 10, 1280x960), using DLE21 and DL2 US 3.19 with HD
media. Both games launched in all four layouts. Captures confirm matching
vertical bezels at opposite edges and video visible behind the transparent Top
scoreboard. Top uses the upstream white digit set with only lit segments,
checked on the cabinet; scoreboards remain outside the CRT-filtered game layer.

Video-less lifecycle probes of DLE21 and DL2 US 3.19 covered single-player and
two-player starts, both turns, elimination, continues, wins, game over, coins
and subsequent games. Twenty runs covered 8.75 virtual hours and 17 checked
lifecycle conditions. DLE21 can retain a nonzero Player 2 score in RAM while
blanking its display in a new single-player game, so numeric RAM values alone
do not establish participation. DL2 initializes both lives slots even in a
single-player game. Its original player count at `0x1000:56a6` distinguishes
participation and clears at match end; `0x56a4` can shrink during a two-player
match and must not be used for this purpose.

The DL2 adapter uses that original count to hide inactive numbers. Both scores
appear immediately in a two-player game; finished players keep their score but
have blank lives until the whole match ends, when all player numbers disappear.
Fixed artwork labels remain. DL1's score retention and initial delay before
showing Player 2's score are deliberately not reproduced, nor is extra blinking.
`python3 android/tests/test_dl2_scoreboard.py` compiles the production adapter
against a capturing scoreboard and checks 14 lifecycle/boundary cases, including
continues after Player 2 is eliminated and stale scores in a new match.
Eight additional video-less DL2 ROM runs exercised the production adapter at
the driver's normal scoreboard IRQ, with assertions on every repaint (3.44
virtual hours). These included the paid-continue case where the original player
count remains two while the current player limit drops to one; Player 2's score
must remain visible and their lives blank. All assertions passed.
These visibility rules require no changes to the ROM, CPU or input timing.
They have not yet been checked visually on the cabinet.

## Move policies and Watch Mode

European Dragon’s Lair (`laireuro`) has 704 decoded records and 592 shared
ranked rules. Across all four operator levels, both strategies passed two start
times and three queue phases: 48 death-free host plays and 48 independent
physical-input replays. Each normal run finished with 207 presses and 202,599
points. All 36 room-queue entries were observed, with different room orders
between start times. Both strategies select the same first-ranked action at every record;
this does not prove a global optimum over ROM dispatch or other settings.
Eight deliberate-miss recovery cases (four levels, both strategies) also passed
their independent replays, finishing with two lives, 210 presses and 203,649 points.

The European ROM has one out-of-range default link: record 648 targets 8043
without input, while UP targets valid record 649. The complete inventory retains
this raw link; safe policies exclude it without replacing its destination.
Withholding that UP in a natural run reached record 8043, and the verifier
correctly returned failure. Victory now requires a decoded victory record and
its playing ending clip, rather than a RAM flag alone. The same stricter
verifier passed all 48 Italian difficulty cases; its move data is unchanged.
The combined revision catalog is checked with a European-only record that must
not select an Italian action. Bundled validation reconstructs both full policies
and checks the compiled arrays. Android runtime checks remain deferred.

US Dragon’s Lair revisions A–F passed 96 complete death-free plays and exact
independent replays on each backend (host and Android 9 x86 video-less), covering
both strategies, four operator difficulties and two start times. The generated
host and Android includes match byte for byte. The combined selector passed
144 normal Watch timing cases on each backend, using both strategies and three
queue phases. A further 48 host cases deliberately withheld move 4 and completed
after one life loss. Android recovery checks for these revisions remain pending.
Complete policies are shared where equal: A–D use one rule pool, E–F another;
only byte-identical calibration arrays are shared. A fresh host recheck passed all 48 combinations of revision, difficulty and
strategy at 8 ms queue phase using the updated supplied ZIPs. DLE21 passed both
strategies with its sole fixed difficulty. DL2 passed all five levels through
the production Java player, including one correctly timed native text prompt
per move. These host checks do not replace Android runtime validation.
An explicit PR-7820 port-map
regression protects E020 immediate commands and E010 AY register selection.

Italian Dragon’s Lair has 682 decoded fixed records and 573 shared ranked rules.
The normalized split `lair_ita.zip` plus `laireuro.zip` reconstructs the exact
Italian program used for this export (SHA-256
`5963d613229f84f82bb188622a9ed4c8166d0122d1af2e0a39293c7c5789e42f`).
Both bundled policies and the full inventory match. The offline loader accepts
the parent’s shared chips only after identifying both Italian replacement chips;
synthetic tests reject the European parent as an Italian set. The native loader
already supports this parent/clone arrangement. The European parent has its own separately verified policy, described above.
Across all four operator levels, 48 host cases (two start times, two objectives,
three queue phases) finished without life loss and passed independent replay
of their physical input traces in fresh processes. Different start times gave
69–76 presses and 73,949–88,250 points. Both objectives selected the same actions.
Eight further cases withheld move 4, lost exactly one life, resumed guidance
and finished at 88,051 points; all passed independent replay.
Synthetic checks protect full 16-bit immediate targets, partially loaded records,
death refusal, deliberate waits, the separate Player 2 cutoff, and Euro’s
level-zero bypass for long input windows. Both ROMs’ requested difficulty is
checked in actual ROM RAM (`A18E`); the factory settings are Euro 3 and Italian 0.
The UI calls the existing upstream bank setter and preserves other switch bits.
These tests reuse production European driver/VP932 methods and the shared native
selector, but model the 8 ms poll / 17 ms queue instead of running the production
Java controller. Italian Android runtime and video-backed checks are explicitly
deferred at the maintainer's request.

SAE 1.0 has a separate CRC-pinned exporter layout and runtime policy. Both
objectives passed eight randomized starts at all three skills and both operator
difficulties: 96 complete, death-free plays and independent exact replays on
the host, repeated inside the Android 9 x86 emulator. The host and Android
exports produce identical move tables. Coverage retains all 9,984 decoded
rules and all 2,441 ranked choices; the 156 unranked candidates have no safe
local completion. The three scene-choice lists remain explicit dispatch data.
Using the combined APK selector, both backends passed 54 normal Watch Mode
cases (Off/Max score/Fewest moves and three input phases), plus 24 cases with
a deliberate missed move, including alternate-policy branch detours. These
are fast video-less executions, not cabinet tests or proof of every possible
retry context. SAE's operator skill setting selects the requested skill during
these checks and in the launcher, avoiding a lost momentary skill press.
The signed x86 arcade APK also launched SAE through the launcher with
synthetic video, Hard difficulty, Ace skill, Fewest moves, CRT and the Right
scoreboard. Watch Mode inserted coins and started automatically. Read-only
process-memory samples showed the score advancing from 29,540 to 76,878 with
five lives retained. The skill panel was on the left. This short APK smoke
check does not establish a full video-backed finish or commercial-media sync.
The missing SAE text was a renderer whitelist omission, independent of Watch
Mode input selection. Font initialization now queries the shared move catalog.
Host GLES and software pipeline tests include SAE and Italian calculated text;
this does not claim an Android text screenshot or a physical-cabinet test.

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
- ARM release lint: zero errors, with 42 arcade warnings and 37 mobile warnings.

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
