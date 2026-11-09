# Offline arcade hint generator

Use this laptop tool to generate move hints from supported arcade ROMs. It
runs the game logic and tries input timings without needing the video files.
It advances simulated time as fast as the laptop allows, rather than waiting
for each scene to play in real time.

The tool emulates the Z80 board and the LD-V1000 player's control protocol.
It does not decode video or play audio, and it needs neither SDL nor Android.

## Generate to game completion

Requires Python 3.9+, a C compiler and zlib headers/library (Debian/Ubuntu:
`build-essential zlib1g-dev`). From the repository root:

```bash
python3 tools/offline-hints/hints.py extract \
  --game dle21 --rom /path/to/roms/dle21.zip --output /tmp/dle21.json
python3 tools/offline-hints/hints.py extract \
  --game ace --skill ace --rom /path/to/roms/ace.zip --output /tmp/ace.json
```

Default mode is **campaign**: run the actual game to its successful ending,
without losing any lives. A lost life, failure to reach victory within 3600
simulated seconds, or a process error fails generation and preserves any previous
output. It does not stop after a small node budget. A compiled C executable and
its temporary files are removed afterward. No network or external checkout is
needed; the minimal GPL-3.0 core is bundled with verified file hashes.

Supported sets are DLE21 and Space Ace A3. Chip sizes/CRCs are verified; the JSON
records each chip's SHA-256. Uppercase ZIP member names are accepted. No ROMs or
videos are copied to the output. DL2 3.19 retains the APK's live move-record
decoder; this Z80 tool does not emulate its different CPU board.

Space Ace supports `--skill cadet`, `captain`, or `ace`; generate each separately.
`--start-delay SECONDS` varies the Start press after boot (0–60). Raw hex
`--dsw1`/`--dsw2` bytes override this port's defaults; unlike Hypseus `-bank`,
these bytes are **not inverted**. Free play is enabled and unlimited lives is
disabled. Effective settings are saved in the file.

## How completion is checked

The planner copies CPU, RAM and peripherals, presses candidate inputs and follows
ROM execution. Its 30-second look-ahead requires a further surviving decision or
a recognized successful ending. Timeouts remain unresolved rather than success.
The real campaign follows the selected moves; every life remains accounted for.
A move that eventually loses a life causes the entire campaign output to fail.

For the two exact supported ROMs, success is ROM-driven playback inside the final
victory clips: frames 31080–31180 for DLE21 and 32840–32940 for Ace, while a life
is active. These ranges were checked against the supplied disc media (Daphne
rescued / Borf defeated). The tool never injects a seek to these frames. Normal
extraction needs only the ROMs and simulated frame/status responses, not media.

A completed campaign proves that its recorded sequence reaches that ending. It
**does not mean every possible branch, DIP combination, difficulty, randomized
room order, or second-round variation was explored**. The JSON records this as
`completion_scope: "one death-free campaign"`. Completed runs from several
settings/start times can be combined to increase coverage.

## Put the tables in the APK

```bash
python3 tools/offline-hints/hints.py compile \
  /tmp/dle21.json /tmp/ace.json \
  --require-complete \
  --baseline android/hints/legacy/arcade_moves-android10.inc \
  --output android/app/jni/arcade_moves.inc
```

`--require-complete` checks successful completion, unchanged positive life count
and zero late inputs. The optional baseline preserves earlier coverage. Multiple
JSON files per game are accepted. Conflicting negative evidence is filtered over
the existing matcher's ±24-frame context. Both games must have usable tables;
failed compilation leaves the previous include intact.

Rebuild the APK normally. The compact tables are compiled into the native
library; JSON evidence, CPU explorer and ROM data are **not** packaged in the APK.
The runtime reads the exact current window countdown from live ROM RAM and uses
the table to recognize outcomes. Hints remain synchronized after seeks/retries;
no elapsed-wall-time subtitle track or on-device search is involved.

The checked-in generation and merged-table checksums are recorded in
`android/hints/campaigns/manifest.json`. `run_campaigns.py` reproduces that sweep
and compiles its tables; see `--help`. The bundled sweep completes eight DLE21
campaigns and all three Ace skill levels, retaining the baseline named in the manifest.

## Optional bounded branch exploration

The original exploratory mode remains available explicitly:

```bash
python3 tools/offline-hints/hints.py extract --mode explore \
  --game dle21 --rom /path/to/dle21.zip --nodes 512 --output /tmp/exploration.json
```

`--nodes` bounds snapshots (1–4096); `--sample-ticks` selects the timing sample
step (1–30, default 1; each tick is 131072 cycles at 4 MHz). These options apply
to exploration, not campaign completion. Exploration records failed, ignored and
unresolved inputs as well as bounded continuations. Its `complete` stays false,
and it cannot pass `compile --require-complete`. Interrupted jobs do not resume.
Optional bounded exploration output belongs in `android/hints/offline`, which
is ignored by Git. The committed campaigns, manifest and referenced baseline
are the inputs needed to reproduce the bundled table.

## Tests and provenance

```bash
python3 tools/offline-hints/test_hints.py
python3 tools/offline-hints/verify_roms.py --roms /path/to/roms
python3 android/tests/test_arcade_guidance.py
```

Tests cover snapshot isolation, timer parsing, terminal range/life checks, ROM
rejection, conflict filtering, generated C++ compilation and atomic failure.
The optional ROM test checks deterministic small explorations and unchanged ZIP
hashes. Physical arcade timing remains a separate validation task.

Jeff Nyman's laser-vault core is GPL-3.0, pinned to revision
`1f12c84dfabf3c8e5d028c8804b2f96678c798fa`. Its full license is in `vendor/LICENSE`;
`vendor/provenance.json` records local changes and file hashes. New tool code is
GPL-3.0-or-later. No commercial ROM/media is distributed.

## Retry regression

The runtime and generator share `android/app/jni/arcade_signature.h`. Schema 2
hashes active input descriptors and selected outcomes, excluding unused RAM
slots that change after death. Generated documents record the header checksum.
Keep that path alongside `tools/offline-hints` when extracting the tool archive.
The retained raw table remains a fallback; regenerate canonical records from
ROMs rather than trying to convert old hashes.

```bash
python3 tools/offline-hints/test_retries.py --roms /path/to/roms
```

This test runs faster than video time, deliberately misses inputs after 1, 5,
and 20 moves in both DLE21 and Ace, loses two lives, then resumes the oracle.
Each resulting live move is checked against the actual production C++ decoder.
RAM snapshots stay in temporary memory; only counts are written with `--report`.
This checks retry recognition, not exhaustive branch coverage or Android UI/audio.
