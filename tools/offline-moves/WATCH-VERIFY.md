# Watch Mode verification

The ROM-derived route and the Android player answer different questions. A
successful route proves that a sequence works at its recorded delivery times.
It does not prove that an IRQ-published move, a Java polling callback and SDL's
input queue will deliver that sequence at those same times.

## DLE21 and Space Ace

`cost_runtime.py` reconstructs complete cost-plus-future policies and independent
Bellman certificates for all supported skills and operator settings. See
[COST-FUTURE.md](COST-FUTURE.md) for generation and optimality audits.
Pass its `arcade_moves.inc` to `verify_watch_moves.py` with `--include` to
check the generated bundle before publishing it. The Watch Mode checker
then tests the APK's merged lookup with IRQ publication, 8 ms Java polling,
100 ms holds and SDL's 17 ms queue cadence. Queue phases 0, 8 and 16 ms are
tested by default. Use repeated `--input-phase` arguments for focused checks.

The checker uses only the packaged ROM-derived rows. It does not learn moves,
consult a teacher, or silently repair a missing state. Fix a failure in the ROM
extraction/generation or timing model, regenerate the bundle, and rerun the
checks. Complete ROM tables supply the policy; independently replayed full
games supply host-only timing measurements and execution evidence.

Both strategies retain the complete set of ranked ROM alternatives, including
branches and retry steps absent from sampled winning games. The bundler ranks
the continuation at each scene/step using the selected ROM policy, regardless
of which strategy originally reached it. It preserves a policy's deliberate
choice to wait, rather than inserting an optional action from the other policy.
This lets guidance resume after an alternate action or a lost life.
The source bundle retains complete graphs and value certificates. The APK stores only
the complete ranked rule pool and a 16-bit index list for each strategy, with
identical arrays shared across ROM revisions. Timing comes from live ROM state. Each list keeps that strategy's original priority order; the
runtime binary search follows the indices without copying or expanding rows.
The bundle checks verify index bounds, ordering and complete use of the pools.

On the host, each successful case records its actual CPU advances and physical
input events. A fresh process then replays that schedule without consulting the
policy and must match the final machine hash, score and native accepted-input
count. Successfully checked schedules are temporary and removed; failed schedules
remain for diagnosis. `moves` counts attempted pulses, while Space Ace's
`accepted_commands` counts original-ROM acceptance. Use the latter when checking
its Fewest moves bound. `optimality.py --watch-report REPORT` requires an attaining,
independently replayed execution for every one of the 36 Space Ace objectives.

To exercise that recovery, add `--game ace --mode 1 --mode 2 --detour 1` to
the checker. At the first decision where the two strategies offer different
inputs, it follows the other strategy for that state, then resumes the selected
one. `--detour 2` and higher target later differences; repeated arguments check
several detours independently. `--detour 0` checks ordinary play. The report
separates requested detours from those actually exercised: a target beyond the
available differences is a normal replay, not evidence of branch recovery.
These detours use only the bundled rows and the production selector. They do
not use the simulator's ROM-policy player to supply missing actions.
Use `--jobs 2` to run two independent replays concurrently. Each replay has its
own emulated machine; concurrency does not change its virtual timing.

Use `--include /path/to/candidate.inc` to test a candidate without replacing the
APK input. `--android emulator-5556` compiles and runs the same check on Android.
The source arrays carry scene/step and branch context; operator DIP settings
are applied to the machine rather than guessed from the currently visible
prompt. A successful finite matrix does not prove every possible retry context
or a global optimum.

## Recovery after a lost life

Normal-start victories do not test retry scenes. Deliberately withhold a move
until one life is lost, then require a full finish without another loss:

```bash
python3 tools/offline-moves/verify_watch_moves.py \
  --roms /path/to/roms --output local-tools/watch-retry \
  --starts 1 --miss-at 20 --jobs 2
```

Add `--android emulator-5556` for the Android backend. The checker uses only the
bundled policies and live ROM timers, with no teacher or learned repair. Repeat
with different `--miss-at` values to sample other retry routes. Each positive
result must report exactly one intended death and a completed recovery.

## European and Italian Dragon's Lair

`verify_euro_watch.py` exercises the production Java `WatchModeController`, JNI
state publication and packaged policies with the original European Z80, CTC,
DART and VP932 methods. It uses the shared virtual Android clock and models the
17 ms SDL input queue and 125 ms sticky coin queue. It supplies no recorded
inputs or replacement startup player. Video, sound and real-time waits are
omitted; no Android emulator is started.

```bash
python3 tools/offline-moves/verify_euro_watch.py \
  --roms /path/to/roms --output local-tools/euro-watch --jdk /path/to/jdk17
```

The default matrix covers both ROMs, levels 0–3, both strategies and queue
phases 0/8/16. It requires the Java player to insert coins, press Start and
complete a full play with every starting life intact. `--startup-only` instead
stops after three move presses and a positive score; it is a startup regression,
not proof of a completed game. Logs and `report.json` retain counters and source
fingerprints. The ROM loader checks revision CRCs and resolves the Italian
split clone from the adjacent European parent.

Both ROMs test RAM before initializing their interrupt-return stub: at 07A3–07AC,
they copy `EI; RETI` from 0762 to A102. Until those bytes are installed, even
valid-looking packed-BCD credits and lives are test data. The JNI publisher
reports unknown credits and no gameplay during that phase. Afterward, A001
bit 0 distinguishes attract mode from a match. The checker also tests every
uniform RAM byte pattern against the actual publisher before each ROM run.

All games use one Java startup sequence: wait two seconds after native readiness,
insert coins until the credit count increases, retry Player 1 Start and wait
for the ROM's gameplay signal. A credit decrease is not a Start acknowledgment.
The two-second delay is a courtesy, not an assumption that every ROM boots in
two seconds. ROM boot duration and coinage remain controlled by the ROM.
Host success does not validate Android scheduling or decoding load; actual APK
checks through the launcher are still separate and currently deferred.

## Dragon's Lair II US 3.19

Host checks require Python 3.9+, JDK 17, a C++17 compiler and zlib development
headers. They also need the pinned SDL source headers. In a fresh Git checkout,
prepare those sources from the repository root:

```bash
python3 android/bootstrap-deps.py
```

No Android SDK is needed for the host harness once those headers are available.
Android checks additionally require the SDK, NDK and build tools listed in the
[Android build guide](../../android/README.md#build-the-app), plus a running x86
emulator reachable through `adb`.
The commands below use `emulator-5556` as an example serial; substitute the
serial reported by `adb devices` for your emulator.

`verify_dl2_watch.py` uses the production Java `WatchModeController` and JNI
guidance with the original Hypseus i86 CPU and Sony protocol. It extracts the
driver's port, IRQ, EEPROM and input methods from `src/game/lair2.cpp` for each
build. Test clock classes replace Android scheduling imports; the controller
body is unchanged. Video and sound are omitted and virtual time runs as fast
as the CPU permits. Each case starts a fresh process.

```bash
JAVA_HOME=/path/to/jdk17 python3 tools/offline-moves/verify_dl2_watch.py \
  --rom /path/to/lair2.zip --output local-tools/dl2-host --check-prompts

JAVA_HOME=/path/to/jdk17 python3 tools/offline-moves/verify_dl2_watch.py \
  --rom /path/to/lair2.zip --output local-tools/dl2-android \
  --android emulator-5556 --check-prompts
```

Each command covers all five difficulties, three seek delays and three input
queue phases: 45 complete games. `--level`, `--seek-ms` and `--input-phase`
select narrower checks. Reports fingerprint the ROM and source inputs and only
declare success after every planned case has finished.

`--omit-move first` and `--omit-move final` are negative controls: they withhold
one player input and require a detected death. They must never report a win
because a death seek happened to pass the ending's frame number. A positive
completion requires the final ROM record, its ending frame and all initial
lives intact.

The `--check-prompts` check also observes the Sony player's actual third-line
text updates. Every move must produce one nonblank prompt inside the input
window at each difficulty. The harness applies the production Android prompt
configuration, including both the operator-difficulty and per-scene gates.
This checks ROM text generation; it does not measure physical screen latency.

### Acceptance timing

For this CRC-checked ROM revision, the fields in RAM segment `1000` are:

| Offset | Meaning |
| --- | --- |
| `A158` | Disc frame cached by the ROM |
| `A160` | Earliest accepted phase of the current move |
| `A15C` | Later cue threshold; not the opening of acceptance |
| `A15A` | Closing frame, exclusive |

The ROM routines near `2780`/`2790` accept the earlier phases; the routine near
`287C` closes the window. Valid input record types include 0, 1, 4 and 5.
Death records 2 and 3 are excluded.

Waiting for `A15C` sometimes left a single frame for IRQ publication, Java and
SDL delivery. Read-only tracing of an actual APK showed a switch reaching the
board after that window had closed. This was late delivery caused by the wrong
window interpretation, not evidence that Android discarded the input. Using
`A160` exposes the ROM's real acceptance window without changing CPU timing,
adding an arbitrary lead offset or modifying the emulated machine.

The video-less test approximates video frame publication and seek latency; it
does not model decoder workload or arbitrary Android scheduling stalls. Actual
APK runs through the launcher remain necessary to check that boundary. Synthetic
black media can exercise seeks and original ROM logic, but cannot establish
commercial video accuracy or audible synchronization.
