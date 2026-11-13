# Exporting moves from arcade ROMs

`export_rom_moves.py` builds a complete export of the **decoded tables**, rather
than collecting only the moves encountered during successful games. It supports
Dragon’s Lair Enhancement 2.1 (`dle21`) and Space Ace US A3 (`ace`). Other ROM
revisions are rejected. Dragon’s Lair II uses its own ROM move display and is
not an input to this exporter.

The exporter needs Python 3.9 or newer and the ROM ZIP you supply. It needs no
compiler, Android tools, video files, previous move files or successful gameplay
traces. Extraction does not emulate the video or wait for game time.

## Export and verify

Run from the repository root:

```bash
python3 tools/offline-moves/export_rom_moves.py export \
  --game dle21 --rom /path/to/dle21.zip \
  --output local-tools/rom-rules/dle21

python3 tools/offline-moves/export_rom_moves.py export \
  --game ace --rom /path/to/ace.zip \
  --output local-tools/rom-rules/ace

python3 tools/offline-moves/export_rom_moves.py verify \
  local-tools/rom-rules/ace --rom /path/to/ace.zip
```

Choose a new output directory for each export. The tool refuses to overwrite an
existing directory and publishes the package only after checking it. A failed
export does not leave a package that looks complete. Output is deterministic:
the same ROM chips and tool sources produce identical files, independent of
the ZIP’s timestamps, its compression, or the checkout’s absolute path.

Verification checks file hashes, reconstructs rules and rankings from the saved
inventory, and checks the coverage totals. Supplying `--rom` also checks chip
identity and reconstructs the inventory from the original ROM. Without the ROM,
verification checks internal consistency, not authenticity. Hashes are not a
digital signature or proof of correct decoding.

The final statistics include decoded scene slots, unique records, input windows,
ranked candidates, cycles and unresolved targets. An unresolved graph target is
an export error; an unranked candidate is retained and counted.

## What the package contains

| File | Purpose |
| --- | --- |
| `manifest.json` | Format version, chip identities, source hashes, output hashes, coverage totals and limitations |
| `inventory.json` | Decoded records, scene/step aliases and transitions |
| `rules.json` | Every decoded input window and each record’s default transition, with classifications and objective rankings |
| `shortest-policy.json` | Local route choices ranked by fewer actions, then higher score |
| `highest-score-policy.json` | Local route choices ranked by higher score, then fewer actions |
| `shortest.policy`, `highest-score.policy` | The same ranked choices in the existing native player’s `HYPCADE_ROM_POLICY_V1` format |

`rules.json` retains death, empty, ignored and unsupported windows for inspection;
they are not ranked as playable moves. It also retains candidates the local
planner cannot resolve. All valid alternatives remain available, including
actions tied in score and number of moves. Control and window order break ties
deterministically for a player that must choose one action.

The exporter does **not** filter out zero-score transitions. In particular, a
necessary final move in Space Ace must survive even though it awards no points.
An award attached to a target record is recorded as a table fact, not proof that
pressing a control caused that award. Causal acceptance and complete plays still
need simulation against a simultaneous no-input run.

## Reading a rule

The package format is `hypcade-rom-rules`, schema `1`. Each rule has a stable
text ID: `scene:step:ROM-slot:window`, or `scene:step:wait` for a default
transition. This is a ROM-table identity, not a screenshot or video-frame hash.
Separate scene IDs remain separate even when they share a record address.
The exporter does not merge mirrored scenes or assume their controls match.

| Field | Meaning |
| --- | --- |
| `source`, `record_address` | Source scene/step and its ROM record address |
| `rom_slot`, `window` | Input record ordinal and its local window, both zero-based; null for waiting |
| `control` | Up 1, down 2, left 4, right 8, button 16; 0 for waiting; null for unsupported ROM controls |
| `outcome`, `target`, `dispatch` | Original outcome and its structural destination; bit 7 dispatches to scene/step 0, including a restart of the same scene; 255 means ignore |
| `loader` | Original control, header, selector and optional condition field, for interpretation by the original ROM loader |
| `timing` | Original delay, current window length and preceding window lengths, in ROM ticks before runtime adjustments |
| `classification` | Candidate, death, empty window, ignored, unsupported control, unresolved target, or source handled by ROM dispatch |
| `objectives` | Available ranks and remaining score/action estimates for each objective; an empty object means no local ranking was established |
| `source_award`, `target_award` | Awards encoded by the records, not measured causal gains |

For `source-dispatch` records, the stored outcome byte is preserved but `target`
is null. Death, scene-exit and system dispatch are controlled by ROM code; their
trailer bytes must not be interpreted as ordinary timeout edges.

**ROM slots are not runtime slots.** Space Ace can skip input records according
to its current conditions and adjust timers for skill and other state. An
application must match a rule against the live ROM-loaded input records, rather
than indexing live RAM directly with `rom_slot`. The optional condition byte
is preserved; this exporter does not claim to have independently implemented
all loader conditions.

Likewise, a timer window’s existence does not establish the first instant at
which a press is accepted. `accepted_frame` is deliberately null. Do not turn
these original tick counts into an absolute video frame without runtime
validation. This avoids baking a timing measurement from one play into all
future plays.

## Validate with the original ROM

The existing headless player can consume the package after verification:

```bash
python3 tools/offline-moves/rom_moves.py \
  --game ace --rom /path/to/ace.zip \
  --rules local-tools/rom-rules/ace \
  --output local-tools/rom-rules-validation/ace --starts 8
```

This stage needs a C11 compiler and zlib development headers. It runs the original
CPU and player without video, audio or real-time delays, then independently
replays each completed route. It prints progress and preserves failures.
Space Ace runs all three skills unless `--skill` selects one. Use different
`--seed` values to sample more randomized starts. Test post-death contexts
separately; normal-start victories do not establish retry coverage.

That focused command uses the default operator difficulty. Before packaging,
use `verify_rom_matrix.py` to regenerate the exports and test both objectives at
every supported skill and operator difficulty. On success it directly writes
one merged JSON file per game and the APK include into its output
directory. Follow the commands in the
[tool guide](README.md#generate-both-move-sets), then run unassisted Watch Mode
checks. [Watch Mode verification](WATCH-VERIFY.md) explains the additional input
delivery timing checks and the corresponding Android runs.

The exported policies optimize paths to local scene exits. Runtime scene ordering,
conditional inputs, system dispatch and cycles limit that model. They are not
proof of a global maximum score or minimum number of moves. Exporting every
decoded window is also not proof that every reachable scene has been decoded.

## Relationship to the APK

This is a structural rules package, not a replacement for the current
`ArcadeRomMove` pools and strategy index lists in `android/app/jni/arcade_moves.inc`.
Those pools contain accepted timings from verified plays. The complete
`verify_rom_matrix.py` extraction workflow generates that shared representation
automatically through `bundle_rom_moves.py`, which also publishes checked
outputs into the APK source tree. Its coverage remains limited to the collected
runtime contexts. A structural-only export does not modify APK inputs.

A future direct rules consumer must resolve the original loader’s conditions
and input arming, preserve objective selection, and pass full Watch Mode and
retry tests before replacing the sampled arrays. Exporting more rules alone
does not establish that the current Android player can execute them correctly.

## Keeping the tool in Git

Keep `export_rom_moves.py`, this document, `test_rom_export.py`, `rom_tables.py`
and `moves.py` in the repository. The existing player and its vendored CPU sources
are also needed for execution validation; preserve their provenance and licenses.
The synthetic tests require no commercial ROM:

```bash
python3 tools/offline-moves/test_rom_export.py
python3 tools/offline-moves/test_rom_tables.py
```

Keep ROM ZIPs, videos, scratch exports and local execution logs under ignored
`local-tools/`, outside the public source set. The manifest contains chip hashes
and decoded information, but no ROM chip payloads, local absolute paths or
signing data. Review any generated artifacts separately before publication.
The exporter additions are GPL-3.0-or-later, like the other Hypcade tools.
