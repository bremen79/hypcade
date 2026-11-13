# Watch Mode verification

The ROM-derived route and the Android player answer different questions. A
successful route proves that a sequence works at its recorded delivery times.
It does not prove that an IRQ-published move, a Java polling callback and SDL's
input queue will deliver that sequence at those same times.

## DLE21 and Space Ace

`verify_rom_matrix.py` tests both extracted policies at every supported skill
and operator difficulty, including independent replays, then directly writes
one merged JSON file per game and `arcade_moves.inc` into its output
directory. Pass that include to `verify_watch_moves.py` with `--include` to
check the generated bundle before publishing it. The Watch Mode checker
then tests the APK's merged lookup with IRQ publication, 8 ms Java polling,
100 ms holds and SDL's 17 ms queue cadence. Queue phases 0, 8 and 16 ms are
tested by default. Use repeated `--input-phase` arguments for focused checks.

The checker uses only the packaged ROM-derived rows. It does not learn moves,
consult a teacher, or silently repair a missing state. Fix a failure in the ROM
extraction/generation or timing model, regenerate the bundle, and rerun the
checks. Independently replayed full games remain the source of every row.

Both strategies draw from the same set of verified branches. The bundler ranks
the continuation at each scene/step using the selected ROM policy, regardless
of which strategy originally reached it. It preserves a policy's deliberate
choice to wait, rather than inserting an optional action from the other policy.
This lets guidance resume after a player takes a different verified branch.
Each merged JSON contains its move pool and both strategy lists. The APK
stores one pool of unique rows per game and a 16-bit index list for
each strategy. Each list keeps that strategy's original priority order; the
runtime binary search follows the indices without copying or expanding rows.
The bundle checks verify index bounds, ordering and complete use of the pools.

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
  --rom /path/to/lair2.zip --output local-tools/dl2-host

JAVA_HOME=/path/to/jdk17 python3 tools/offline-moves/verify_dl2_watch.py \
  --rom /path/to/lair2.zip --output local-tools/dl2-android \
  --android emulator-5556
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
