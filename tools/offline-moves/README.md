# Offline arcade move tools

These laptop tools reconstruct moves for Dragon’s Lair Enhancement 2.1 (DLE21),
US Dragon’s Lair revisions A–F, Space Ace US A3 and Space Ace Enhancement 1.0.
They run the original Z80 ROM with a simulated LD-V1000 or PR-7820,
without opening video/audio or waiting for real time. Commercial ROMs and media
are not included. The APK does not contain ROM payloads.

For a complete export of the decoded tables, independent of sampled games, use
[the ROM rule exporter](ROM-EXPORT.md). It preserves unvisited branches, timing
windows and all alternatives, with separate rankings for both objectives.
The APK uses its complete ranked policies. Sampled successful plays add timing
calibrations; they never limit which scenes or retry moves are available.

## Generate both move sets

Use Python 3.9+, a C11 compiler, zlib development headers and the ROM ZIPs you
already own. No Android SDK is needed for generation.

```bash
python3 tools/offline-moves/verify_rom_matrix.py \
  --roms /path/to/roms --output local-tools/rom-moves --starts 8 --jobs 2
```

The directory must contain `dle21.zip` and `ace.zip`. This runs both objectives
for DLE21 and for every combination of Space Ace's three skills and four
operator difficulty settings: 208 complete games, each followed by an independent
exact replay. Space Ace's operator difficulty controls when and how the game
speeds up; it is separate from Cadet, Captain or Ace. DLE21 has no difficulty
selector.

For SAE alone, use `--game sae --rom /path/to/SAE_10.zip` instead of `--roms`.
The same eight-start check covers all three skills and both Easy/Hard settings
(96 games, each independently replayed). SAE has its own layout and policy;
it does not reuse A3's moves. For a combined cold export, repeat `--game` for
`dle21`, `ace` and `sae`, with a directory containing each `GAME.zip`.
The runtime ROM catalog can point aliases at one set of arrays, so identical
policies need not be copied for every revision.

For US Dragon’s Lair, use `--game lair_a --rom /path/to/dl_reva.zip`, and
similarly `lair_b` through `lair_f`. Each revision covers all four operator
difficulties. A–C use the PR-7820 board adapter, D–F the LD-V1000 adapter.
`rom_tables.py` is the single source for chip pins and board defaults; the
generated `rom_catalog.inc` keeps the C verifier in agreement. The pinned
vendor sources are unchanged. To combine independently verified exports, use
`merge_rom_bundles.py --input FIRST --input SECOND --output COMBINED`.
It retains each export's evidence and source fingerprints, then shares
identical immutable arrays. Different timing arrays remain separate.

## Italian European-board Dragon’s Lair

This ROM uses PAL timing, a European board and the serial VP932 player, so its
fixed records need their own decoder. Generate and check both strategies with:

```bash
python3 tools/offline-moves/euro_moves.py \
  --rom /path/to/dl_italian.zip \
  --output local-tools/italian-moves --starts 4
```

The tool checks four program-chip CRCs, decodes every fixed record, and runs
both policies with 0/8/16 ms input-queue phases. Starts use different delays to
exercise ROM route selection. Each completed run is independently replayed
from its recorded physical inputs in a fresh process, without consulting moves
to choose inputs. The shared native selector runs at the driver's 50 Hz tick,
with modeled 8 ms polling, 100 ms holds and 17 ms input delivery. This is a
host timing model, not execution of the Android Java controller or an APK test.
No video, sound, real-time waits or previous move files are used.

Check recovery separately with `--miss 4 --input-phase 8`. The tool withholds
that move and requires a finish after exactly one lost life. Failed checks do
not publish a bundle. Successful normal checks write `bundle/`, containing
one shared rule pool, both strategy index lists, the complete inventory,
verification and hashes. Identical strategy lists share one native array.
Only `arcade_euro_moves.inc` is compiled into the APK; program bytes remain
private test data. The small Android driver hook only reads state. CPU timing,
CTC/DART and VP932 protocol behavior are unchanged.

The Italian tests currently use the native factory operator settings. Android
emulator and video-backed checks are pending; host success does not substitute
for them. See [the format notes](ROM-EXPORT.md#italian-european-records).

The report includes each setting, start delay, score, move count and pass/fail
result. Both `shortest` and `highest-score` routes retain their separate evidence.
After every case, independent replay and complete ROM coverage check passes,
the same command writes one merged JSON file per game, `manifest.json` and
`arcade_moves.inc` directly into the output directory. A failed matrix does not
publish a move bundle. Route evidence is reused in place rather than copied
into a second output tree.
For a smaller diagnostic run, use `--starts 1`. Fewer starts reduce timing
validation, not structural coverage: all decoded rules and ranked alternatives
are packaged regardless of which scenes appear. Never describe a partially
finished report as a successful matrix.

Check the packaged policies against every decoded ROM rule:

```bash
python3 android/tests/test_bundled_moves.py --roms /path/to/roms
```

The command fails if any decoded window or ranked alternative is omitted. Its
coverage report is independent of sampled winning runs. Non-playable inputs
remain in the audit with explicit exclusions; a safe unranked continuation is
an error, not an acceptable coverage gap.

`rom_moves.py` remains useful for a focused single-game test at the default
operator difficulty, but its report is not the full-matrix input to the bundler.

The tool validates chip names, sizes and CRCs before using revision-specific ROM
layouts. Other revisions need their own validated layout; the tool refuses to
interpret an unknown ROM as DLE21 or A3.

## How reconstruction works

1. Decode the ROM’s scene/step pointer tables and compact input records.
2. Extract timing windows, input outcomes, default transitions, score awards and
   death/scene-exit flags. Keep all input alternatives, including equal outcomes.
3. Rank local paths separately for fewer actions and higher scores. Waiting costs
   no action. Never discard a required action merely because it gives no points.
4. Boot the original ROM and use its normal scene selection, timing and inputs.
   A press needs causal score or scene/step evidence against no input. Deferred
   acceptance is checked beyond a mere change of the visible prompt.
5. Replay each complete winning trace independently and check exact states,
   timing, score and absence of life loss.

The policies optimize local table paths to scene exits. The ROM still decides
scene order and context. Cycles, system dispatch and unreachable entries prevent
these results from being a proof of the globally shortest or highest-scoring
possible game. An inventory entry is not necessarily a distinct playable room:
there are aliases, system records, death clips and prototype-only entries.

## Check and publish the generated moves

Check the directly generated include before replacing the APK's inputs:

```bash
python3 tools/offline-moves/verify_watch_moves.py \
  --roms /path/to/roms --output local-tools/watch-moves --starts 2 \
  --include local-tools/rom-moves/arcade_moves.inc
```

After those checks pass, publish the verified bundle into the APK source tree:

```bash
python3 tools/offline-moves/bundle_rom_moves.py --results local-tools/rom-moves
```

The extraction command and this publishing command use the same bundler; no
separate merging or format-conversion step is needed.

The generator and bundler supply complete ROM rules and ranked policies, plus
timing calibration from independently replayed games. The Watch Mode checker
uses only that packaged data; it cannot
fill missing moves from a teacher or learned fallback. A missing state or failed
play must be fixed in generation and then checked again. Keep failures visible;
do not publish an unfinished pass.

With the default three queue phases, `--starts 2` runs the 234-case Watch Mode
batch recorded in the validation reports. Use `--starts 8` for an extended
936-case batch; those extra starts are additional checks, not part of the
recorded 234-case result.

Each merged game file contains a unique move pool and both 16-bit strategy
index lists. Publishing writes that representation to
`android/app/jni/arcade_moves.inc` and saves the matching JSON and route evidence
in `android/moves/rom-tables/`. Scene and step locate the complete ROM policy;
live loaded controls, outcomes and window timers determine the applicable move.
Optional timing calibration also distinguishes Space Ace branch bytes. The Watch Mode check exercises the same selector
with IRQ guidance, 8 ms input polling, SDL’s 17 ms input-queue cadence and
100 ms button holds. It varies the queue phase independently of randomized
starts. Mode Off uses the
Max score policy for automatic play. This headless test is not a physical-device
test, and normal-start games do not prove every post-death context.

## Check the same cases on Android

With the existing x86 Android emulator running, repeat the matrix using its
native Android build and then check the packaged selector:

The examples use `emulator-5556`; replace it with your emulator's serial from
`adb devices`.

```bash
python3 tools/offline-moves/verify_rom_matrix.py \
  --roms /path/to/roms --output local-tools/rom-moves-android \
  --starts 8 --jobs 2 --android emulator-5556

python3 tools/offline-moves/verify_watch_moves.py \
  --roms /path/to/roms --output local-tools/watch-moves-android \
  --starts 2 --android emulator-5556 \
  --include local-tools/rom-moves-android/arcade_moves.inc
```

These use the shared SDK's NDK; they do not install another toolchain. They run
without video or real-time waits, inside Android. They are separate from actual
APK tests through the launcher, which also exercise SDL, media decoding and
Android scheduling. Neither type is a physical cabinet test.

For DL2's ROM-native prompts, production Java player tests and the interpretation
of its input windows, see [Watch Mode verification](WATCH-VERIFY.md).

## Shared simulator and checks

`rom_tables.py` decodes and ranks the ROM tables. `simulation.c` supplies the
headless machine helpers, while `score_routes.c` and `score_trial.h` handle
input trials and exact replay. `score_routes.py` builds and invokes that verifier;
it is not a separate gameplay-search command. The ROM player and Watch Mode
checker share these helpers so they validate the same CPU/player behavior.

```bash
python3 tools/offline-moves/test_rom_tables.py
python3 tools/offline-moves/test_score_routes.py
python3 tools/offline-moves/test_rom_export.py
python3 tools/offline-moves/test_moves.py
python3 android/tests/test_bundled_moves.py
```

## Source and attribution

The minimal Z80/Cinematronics/LD-V1000 implementation is adapted from Jeff Nyman’s
GPL-3.0 laser-vault, pinned in [vendor/provenance.json](vendor/provenance.json).
Original notices and the component license remain in [vendor/NOTICE](vendor/NOTICE)
and [vendor/LICENSE](vendor/LICENSE). Hypcade’s additions are GPL-3.0-or-later.
Source verification checks the vendored files before building. Keep the adjacent
`android/app/jni` shared headers when using the tools outside this checkout.
