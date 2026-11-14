# Exporting moves from arcade ROMs

`export_rom_moves.py` builds a complete export of the **decoded tables**, rather
than collecting only the moves encountered during successful games. It supports
Dragon’s Lair Enhancement 2.1 (`dle21`), Space Ace US A3 (`ace`) and
Space Ace Enhancement 1.0 (`sae`), plus US Dragon’s Lair revisions A–F
(`lair_a` through `lair_f`). Unlisted ROM revisions are rejected.
European and Italian board ROMs use the separate exporter described below.
Dragon’s Lair II uses its own ROM move display and is
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

For SAE, use `--game sae --rom /path/to/SAE_10.zip`. The ZIP filename does
not determine the revision: the five `sae10_u*.bin` chip names, sizes and CRCs
must match. Case differences in chip filenames are accepted.

US A–D use the scene roots at `0x3922` and score table at `0x38B4`;
E uses `0x1FD3` / `0x1F65`, F `0x2108` / `0x209A`. A–D policies share
identical native rule arrays, as do E–F. Calibration arrays are only shared
when their complete contents match. Similar-looking scenes alone never justify
merging move or timing data.

SAE has its own scene roots at `0x2571` and score table at `0x2503`.
Its common input loader uses the same compact records as A3, including
conditional trailer fields and doubled score awards. Of its 80 root slots,
the last three contain terminated scene-choice byte lists rather than step
pointer arrays. The inventory preserves these lists as `dispatch` groups;
they must not be decoded as input records. The original ROM executes them.

To generate both ranked strategies and independently replay full games for
all three skills and both SAE difficulty settings:

```bash
python3 tools/offline-moves/verify_rom_matrix.py \
  --game sae --rom /path/to/SAE_10.zip \
  --output local-tools/sae-moves --starts 8 --jobs 2
```

This writes a separate SAE move pool, both strategy index lists, complete rule
audit and timing calibrations. Generation alone does not change the APK bundle.
Explicit output paths are required when publishing
a non-default game set, to avoid replacing the existing DLE21/A3 bundle.
SAE's Easy/Hard switch controls recovery after death; its three skills choose
different routes. Test both settings even though death-free runs can agree.

`merge_rom_bundles.py --input FIRST --input SECOND --output COMBINED` combines
disjoint, verified export directories without recalculating unchanged games.
Each input must contain its `arcade_moves.inc` and matching manifest. The tool
checks complete coverage and replay evidence before and after merging, and
retains the original generation reports and source fingerprints. It does not
claim older evidence was produced by a newer generator. The combined catalog
uses the same selector as a single matrix export.

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

The APK contains the complete ranked policies generated from these tables.
`bundle_rom_moves.py` retains every decoded rule in the merged game JSON file,
including unvisited scenes and retry-only steps. Native rule pools and compact
strategy indices include every ranked alternative, including deliberate waits.
The player chooses one applicable action at a time.

Successful simulations supply additional timing calibrations for observed
contexts. They do not decide whether a rule is included. For an uncalibrated
context, the selector matches the live ROM-loaded control, window and outcome;
the ROM remains responsible for conditional record loading and skill-dependent
timers. Absolute frames and branch bytes from a sampled game are not required
for guidance to continue after death or an alternate action.

Check complete coverage independently of gameplay:

```bash
python3 android/tests/test_bundled_moves.py --roms /path/to/roms
```

This reconstructs every rule and ranking from the saved inventory and, with
`--roms`, decodes that inventory again from the supplied ZIPs. Removing any rule
or ranked alternative fails verification. Coverage also accounts for windows
that lead to death, ignored inputs, empty windows, system dispatch, diagonal
controls with equivalent single-control outcomes, and paths with no safe local
completion. These remain auditable rather than being displayed as good moves.
An unranked rule with a safe structural continuation fails packaging.

Structural completeness and successful execution are separate checks. Run the
skill/difficulty matrix, varied input timing, branch detours and deliberate
life-loss recovery on the host and Android emulator before shipping a bundle.

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

## European-board records

Use `euro_tables.py --game laireuro --rom /path/to/laireuro.zip --output OUTPUT`
(or `--game lair_ita` for the Italian clone) for a structural export, or `euro_moves.py` for extraction plus independent replay.
This is a separate format, not a special case in the Cine compact decoder.

Four 8 KiB program chips are CRC-pinned. A complete Italian ZIP contains all
four program chips; a split `lair_ita.zip` contains only the Italian 45/48
replacement chips and reads the shared 46/47 chips from an adjacent
`laireuro.zip`. Both layouts reconstruct the same Italian program. The two
Italian replacement CRCs must be present in the selected ZIP; the European
parent is never accepted as an Italian revision. The native game also needs
the parent ZIP for its shared character graphics.

At `0x2000`, the ROM stores its 36-room queue and system-entry record IDs. Records are one-based, 32 bytes
each, starting at `0x2088`. Both pinned revisions end at ID 704.
The Italian ROM has 682 nonempty records;
the European parent has all 704, including an additional sequence absent from
the Italian table. The European first/fourth program CRCs are `4D3A9EAC` and
`36575106`; the Italian replacements are `2ED85958` and `0C0B3011`.

| Record offset | Meaning |
| --- | --- |
| 0–1 | PAL starting frame, little-endian |
| 2 | Flags: `0x10` death, `0x40` victory; `0x20` alone does not identify every input window |
| 3 | Duration in PAL frames |
| 4–5 | Packed BCD award, little-endian word |
| 6–29 | Twelve little-endian input targets; `0xFFFF` means ignored |
| 30–31 | Default next record; zero returns to ROM room dispatch |

The ROM input handler maps target slots 7/6/5/4/3 to Up/Down/Left/Right/Button.
Other slots must be unused or extraction fails. Target bit 15 requests an
immediate transition; it is preserved, while the low 15 bits identify the
destination. Root destinations must exist. Out-of-range transition targets
remain explicit
`unresolved_targets` in the inventory and are excluded from safe continuations.
No destination is guessed or patched. The pinned European ROM has one such
default target: record 648 points to 8043 if no action is taken, while UP leads
to the valid record 649. Withholding that UP in natural execution reaches the
invalid record, and the verifier rejects it rather than treating corrupt RAM
as a victory. Deaths are excluded from safe policies; required zero-score transitions remain. Cycles are rejected
explicitly rather than silently dropping alternatives. Both strategies rank
all safe alternatives at every record, including records absent from sampled
plays. Rankings optimize continuations to a ROM room-dispatch boundary, not
the ROM's globally randomized route.

At runtime, `A17A` holds the current record, `A10F` its starting frame,
`A112` its remaining frames and `A115` its input target list. The native
selector checks that record loading has completed and matches the full target.
The accepting test reproduces the ROM's `CP` / `RET M` sign-bit test against
`A189` for Player 1 or `A289` for Player 2, selected by `A152`.
It does not replace this with an unsigned comparison. Scores are packed BCD
at `A142`–`A144` / `A145`–`A147`; lives are `A149` / `A14A`, credits `A14B`.
The verifier extracts the production European driver and VP932 methods rather
than substituting the US board or inventing video timing.

## European and Italian operator difficulty

Upstream `laireuro::set_bank` already accepts both physical switch banks.
No new engine option or ROM patch is needed. Both pinned programs complement
the byte read from `E090` and shift it right six times into `A18E`. Thus bank A
bits 6/7 select operator levels 0–3. The Android catalog changes only raw mask
`0xC0`, preserving coinage, lives and the other bank. Euro’s factory raw bytes
are `16 F6` (level 3); Italian’s are `DF EF` (level 0).

These are operator settings, not a replacement for the ROM’s progression.
The European ROM starts its global current level at `A18F` from `A18E`;
Italian starts per-player levels at `A18F` / `A28F` and ramps them according
to the operator setting. Euro’s input handler bypasses the timer comparison
at current level zero and otherwise uses global cutoff `A189`. Italian always
performs the signed comparison against the current player’s cutoff at
`A189` / `A289`. The shared selector follows this distinction, including long
input records whose remaining frame count has its high bit set.

DLE21 is different: its supplied `readme21.txt` explicitly removes difficulty
options. Its prototype mode is a separate game mode, so the Android menu does
not mislabel that switch as difficulty. US A–F retain their existing four
operator choices; DL2 US 3.19 retains its five EEPROM levels.
