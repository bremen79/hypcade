# ROM record extraction

Use [the cost-plus-future generator](COST-FUTURE.md) for production policies.
Its source bundle includes complete decoded inventories, both calculated
rankings, independent Bellman values and output/source fingerprints. The
[retention rule](COST-FUTURE.md#policy-retention) then selects which complete
rankings enter the APK and its generated UI catalog.
The former standalone local-search exporter and bundle merger are removed.

`rom_tables.inventory(rom, game)` decodes Cine scene/step pointer tables and
compact input records; `euro_tables.inventory(rom, game)` decodes the European
board’s fixed records. Chip names, sizes and CRCs identify supported revisions.
No sampled successful route limits either inventory. Unknown layouts and
unresolved destinations must fail validation.

US A–D scene roots are at `0x3922` and the score table at `0x38B4`;
E uses `0x1FD3` / `0x1F65`, F `0x2108` / `0x209A`.
SAE scene roots are at `0x2571`, its score table at `0x2503`.
Its last three root slots are terminated scene-choice lists, not step arrays.
SAE scores are doubled; flagged accepted inputs can restore score awards
following a death. A3 uses a separate fixed-award transfer rule.

Loaded input descriptors retain delay, consecutive windows, control, outcome
and flags. `rom_controls.accepted_regions` respects original descriptor
priority and ignores empty/shadowed/FF outcomes. The inventory retains diagonal
entries for auditing; generated policies use cardinal/button inputs only.
Timing remains in the running ROM rather than being copied into strategy rows.

For a Cine inventory only:

```bash
python3 tools/offline-moves/rom_tables.py --game lair_a \
  --rom /path/to/lair_a.zip --output local-tools/lair-a-inventory
```

For A3 or SAE the same entry point writes contextual cost-plus-future outputs.
Use `cost_runtime.py` for the unified eleven-ROM production bundle. Verification
without ROM files checks internal consistency; `--roms` additionally reconstructs
inventories and context graphs from the CRC-validated originals. Hashes are not
proof that a transcribed ROM rule is correct: bounded original-CPU audits and
independent physical replays supply that evidence.

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
