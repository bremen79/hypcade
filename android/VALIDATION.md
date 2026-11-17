# Validation

This document describes validation of the current implementation and its limits.
Detailed policy results and source fingerprints are indexed in
[the integration summary](moves/verification/cost-future-summary.json).
Build instructions are in the [Android guide](README.md); signed APKs and
checksums are under `android/artifacts/`.

## ROM policies and optimality

The source bundle in `moves/strategies/` contains policies for eleven supported
DL1/Space Ace ROM profiles, complete decoded inventories and independent Bellman
certificates. It does not contain game ROM payloads. The generator is
`tools/offline-moves/cost_runtime.py`; optional analysis tools for additional
ROMs are isolated in `tools/offline-moves/future_roms/`.

The calculated objectives are one-life, death-free play with cardinal directions
or button presses only:

- Fewest moves: the policy can attain the minimum number of accepted commands
  with non-zero possibility.
- Max score: the policy can attain the highest score with non-zero possibility.

Neither objective optimizes an expectation or deliberately spends lives.
Post-calculation [policy retention](../tools/offline-moves/COST-FUTURE.md#policy-retention)
selects which complete rankings enter the APK. The
[retention audit](moves/verification/policy-retention.json) records each decision,
86 recomputed initial objectives and semantic equality of 22 calculated-policy
and proof files, apart from retention metadata. This preserves the applicability
of the mathematical attaining witnesses; it does not substitute for current
runtime delivery checks.
ROM-derived decision graphs, scene-exit continuation costs and scheduler
contracts establish bounds. Independent executions establish attainment of the
primary endpoints: all [50 classic Cine setting/objective cases](moves/verification/classic-attainment.json)
and all [36 Space Ace cases](moves/verification/space-ace-attainment.json) pass
their original-CPU replay checks. Space Ace move counts use
accepted commands, which can differ from attempted input pulses. European and
Italian policies are optimal conditional on the ROM-created room queue.

The [readable ROM policy results](moves/README.md) summarize the
[one-life min/max dataset](moves/verification/one-life-ranges.json), covering
102 ROM/skill/operator/objective combinations. Some US non-primary endpoints
remain unestablished; certified endpoints are identified in the data rather
than treating every support limit as attained. The
[E/F range refinement](moves/verification/late-attained-ranges.json) combines
ROM inventory/Bellman/scheduler calculations, 48 host Watch plays with
independent replays, and eight original-ROM winning replays. A verified
score/input affine invariant establishes accepted-command counts at level 2
without using attempted Watch pulses. A further
[direct acceptance-count refinement](moves/verification/counted-attained-ranges.json)
adds six endpoints from 43 independently replayed plays. Its read-only observer
recognizes the ROM's accepted-outcome instruction after rejected-input checks;
the independent replay must reproduce the accepted count. Ten common cases
also retain the complete-state hashes of the uninstrumented checker. These
refinements add 22 attained endpoints in total. They are host-only and do not
change the APK policies or their runtime validation. Italian
pool-wide enclosures do not prove joint RNG attainment. These qualifications
are part of the reported scope, not guarantees about every random sequence.

The build gate checks every ranked alternative, both native includes and the
independent Bellman certificates. With supplied ROMs it also reconstructs the
inventories and contextual transition/reward graphs. Coverage comes from the
complete decoded rules, including retry states and necessary zero-score
transitions, rather than a collection of successful sampled routes. No diagonal
input is selected. Runtime timing is derived from the loaded ROM descriptors;
there are no calibrated replay timing arrays in the packaged policies.

Shared rule pools retain revision guards. European/Italian rules keep full
16-bit targets and their own difficulty cutoffs, including the European
level-zero bypass and Italian per-player cutoff. The European inventory retains
its invalid no-input link from record 648 to 8043; safe guidance uses the valid
UP transition to 649. Invalid destinations are not silently repaired.

DL2 is excluded from this optimization and uses its own ROM prompts. US 3.19
acceptance starts at segment `1000`, offset `A160`; `A15C` is a later cue threshold
and `A15A` is the exclusive closing boundary. Record types 0, 1, 4 and 5 are
supported. Its retained [validation reports](moves/verification/dl2/) have not
been rerun for the current integration and do not certify the current APK.

## Watch Mode matrices

The matrices exercise distinct retained policies. Cine covers DLE21, Space Ace
A3, SAE 1.0 and US Lair A–F, every supported skill/operator setting and queue
phases 0/8/16 ms. European/Italian covers both boards, four operator levels and
the same phases. A single-policy ROM is exercised once per setting/phase,
without replaying its Max/Fewest alias as another policy.

| Check | Host | Android API-25 x86 | Evidence |
| --- | ---: | ---: | --- |
| Cine normal play | 186 | 186 | [Host](moves/verification/cine-watch.json), [Android](moves/verification/android-cine-watch.json) |
| Cine intentional-death recovery | 186 | Not rerun for this integration | [Host](moves/verification/cine-recovery.json) |
| European/Italian Java/JNI play | 24 | 24 | [Host](moves/verification/euro-watch.json), [Android](moves/verification/android-euro-watch.json) |

The Cine harness runs the original CPU/player with IRQ publication, modeled
8 ms controller polling, 17 ms queued input delivery and 100 ms input holds.
Each host case also passes an independent physical-input replay in a fresh
process without policy lookup. The Android native matrix does not run the
production Java event loop or independently replay each trace a second time.
Recovery cases withhold move 20, require exactly one intentional death, then
complete without another loss. This validates functional recovery in the tested
cases, not optimality after a death.

The European/Italian checker runs the production Java Watch controller body,
JNI publisher and packaged selector against the original CPU/CTC/DART/VP932
methods. Host JVM and Android ART runs use a test Handler and simulated clock.
Every case inserts coins, presses Start and finishes with its starting lives
intact. The checker also rejects all 256 uniform RAM-test patterns as credits.
These accelerated runs are distinct from installed-APK gameplay.

All supported Watch games share the two-second initial coin delay and the
coin/Start controller. Gameplay must be acknowledged by ROM state. European
startup publication requires the ROM-installed EI/RETI stub at A102 and the
A001 gameplay bit; RAM-test values cannot acknowledge a start.

For reproduction, see the [offline tool guide](../tools/offline-moves/README.md)
and [Watch verification guide](../tools/offline-moves/WATCH-VERIFY.md).
`verify_euro_watch.py --android SERIAL` uses an already running x86 emulator;
it does not launch one. Saved matrix source fingerprints match the tested
implementation.

## Installed-APK checks

The signed emulator release APKs were launched through the normal launcher and
Watch button, using the actual Java Handler, JNI publisher, SDL queue and
media decoder. Media is synthetic black MPEG-2 video without audio.

| APK / platform | Menu checks | Runtime checks |
| --- | --- | --- |
| Arcade / API-25 x86 | All 12 profiles | All 14 distinct retained policy selections: match started, first two native ready events and no early life loss |
| Mobile / API-35 x86_64 | All 12 profiles | US Lair A On and DLE21 Fewest moves: visible game/score output, touch Exit and return to launcher |

Arcade read-only process sampling confirmed the selected native policy,
visual/Watch flags, ROM match acknowledgment and lives. It did not inject moves
or modify ROM state. Mobile checks use screenshots and process/UI observations,
without RAM inspection. Each game process exited while the launcher remained
available; both test emulators were shut down. Digests and observations are in
[the installed-APK report](moves/verification/android-apk-plays.json).

These are startup checks, not complete installed-APK games. Arcade uses one
saved configuration per ROM, and mobile uses two representative configurations.
The accelerated matrices provide broader settings and full-game coverage.
Neither backend establishes commercial-media synchronization, audible cue
latency or physical-control fidelity.

## Build, packaging and size

All four signed release variants assembled successfully: ARMv7 arcade, ARM64
mobile, x86 arcade emulator and x86_64 mobile emulator. Package inspection
verified the existing release certificate, v0.2.1/code 42, minimum API 25,
target API 36, one ABI per flavor and the exact current native rule/index
arrays. ARM flavor checks also verified fixed arcade landscape and absence of
touch-control code, with mobile controls and orientation policy retained.
Hashes and measurements are in [the APK report](moves/verification/release-apks.json).

Native rule/index payload is 100,462 bytes: a reduction of 6,034 bytes from the
106,496-byte two-policy package, 166,338 bytes against the live-ROM baseline and
352,418 bytes against the calibrated-table baseline. These counts include C
structure padding but exclude catalogs, selector code, linking and APK
compression. The current APK measurements are:

| Flavor | APK bytes | Change from saved two-policy APK |
| --- | ---: | ---: |
| ARMv7 arcade | 5,993,385 | −56 |
| ARM64 mobile | 6,308,471 | −164 |
| x86 arcade | 6,749,201 | +84 |
| x86_64 mobile | 6,761,162 | −120 |

APK compression and the UI changes largely offset the raw table saving; native
payload reduction is not an equivalent APK reduction. Both ARM release lint
checks passed with zero errors and 42 arcade / 37 mobile warnings. Native
compiler and Gradle deprecation warnings also remain.

The 221-test offline unit suite, launcher/control tests, native guidance checks
and full ROM/bundle checks pass. Package checks verify all four final APKs,
including absence of the eight discarded Fewest index arrays. The test planner
has regression coverage for deduplicating effective policies. Documentation
changes do not change the tested native libraries.

## Component regression coverage

The following host checks provide component coverage beyond the full-play
matrices. They do not constitute installed-APK or physical-device validation
of every feature, and the final policy integration did not rerun every component
scenario.

| Area | Checks and scope |
| --- | --- |
| Move decoder and publication | `tests/test_arcade_guidance.py`: acceptance boundaries, supported ROM layouts and guidance state |
| Watch and move audio | `tests/test_watch_mode.py`: startup delay, credit/Start acknowledgment, stale events, held-input release and ready-event cue behavior |
| Launcher and controls | `tests/test_launcher_logic.py`: launch arguments, controller mappings and flavor policies |
| Clock | `tests/test_android_clock.py`: background-aware timing and shutdown timing |
| Scoreboards | `tests/test_dl2_scoreboard.py` and `tests/test_euro_scoreboard.py`: production RAM adapters, player visibility, score/lives formatting and lifecycle boundaries |
| CRT and text | `tests/test_crt_shader.py --native`: production GLES2/software rendering, shared bitmap-font output, game-layer filtering, unfiltered overlays and fallback behavior |
| Storage and media | Asset-path, WAV-packaging and video-index tests under `tests/`; generated fixtures check access and frame advancement |

Calculated DL1/Space Ace text and optional audio use the same native ready
event. The audio callback polls every 16 ms; actual output latency remains
device-dependent. DL2 displays native ROM text and bypasses both prompt gates
when moves are enabled, without a duplicate calculated prompt.

CRT filtering applies to video, ROM text and calculated moves together. Added
score/lives, FPS, subtitles and bezels are drawn afterward without filtering.
Software or unsupported renderers retain the plain path. Host GPU/font checks
cannot establish device-specific performance or display/audio synchronization.

Scoreboard adapters have separate single/two-player component coverage. The
full policy plays above are single-player and do not establish two-player
strategy optimality or every scoreboard/layout combination in the APK.

## Reproduction and acceptance requirements

Follow the [Android guide](README.md) for the pinned toolchain, dependencies,
builds and signing, and the [Watch guide](../tools/offline-moves/WATCH-VERIFY.md)
for ROM matrices and delivery checks. Run checks appropriate to the changed
area; documentation-only edits do not require an APK build. Keep Gradle builds
sequential and do not launch an Android emulator unless requested.

Validate the bundled selector using only its packaged rules, without learned
or teacher-assisted fallbacks. Keep causal no-input controls and independent
replays separate from policy construction. Android checks must distinguish
modeled native timing, simulated Java clocks and real installed-APK scheduling;
start installed-APK sessions through the launcher rather than an exported
emulator activity. Compare source fingerprints before attributing saved results
to a changed implementation. Record native diagnostics as well as logcat, and
retain warnings and limitations alongside results. Translated ARM execution
must not be described as execution on physical ARM hardware.

## What remains unproven

One-life optimality has the objective and ROM/queue qualifications stated above.
Optimal continuation after arbitrary deviations, repeated mistakes or deaths,
and later-round optimality are outside the current proof scope. Complete ROM
inventory coverage alone does not establish that every decoded state is
reachable or every input window executable. Recovery matrices demonstrate the
tested recoveries, not every retry branch or optimality after a death.

Synthetic timing media exercises ROM control flow, frame advancement and seeks;
it cannot establish commercial video accuracy or audible synchronization.
Installed-APK startup checks do not establish full-game completion under real
Android scheduling or cover every ROM/settings combination, device,
storage/lifecycle scenario or live scoreboard counter.
A synthetic fixture's `ANDROID_MEDIA_TEST PASS` marker confirms frame
advancement, not commercial-game accuracy.
