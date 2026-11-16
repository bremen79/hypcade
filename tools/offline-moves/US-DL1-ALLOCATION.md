# US DL1 selector composition without room permutations

`dl1_selector.py` executes the **complete** original group-selector routine,
including the descriptor/history lookup, optional-room gate and normal/harder
physical-room routing. It retains all correlated refresh reads inside a call.
`dl1_allocation.py` then solves its selector-support relaxation with a small
resource dynamic program. No probability law is inferred from the support.

```bash
python3 tools/offline-moves/audit_schedulers.py \
  --roms /path/to/roms --output local-tools/scheduler-audit --board classic
python3 tools/offline-moves/optimality.py \
  --roms /path/to/roms --output local-tools/optimality --replay-classic
```

The full extraction checks 589680 original-CPU cases over A–F, raw-bank and
harder-mode paths, all relevant history/optional masks, all 128 refresh seeds
for a reference group, and all eight phase classes for every other ordinary
group. The exact transitions depend on three refresh bits. Each optimal
allocation also passes a chronological 39-room replay through the original
selector/version router. Those routine replays receive explicit refresh seeds;
they are not physical-input gameplay witnesses.

## Revision and instruction-count differences

A's injector tests a history bit through HL. B–D explicitly reload the
harder-mode flag, changing the instruction path. A raw-bank shortcut and a
harder-mode path can logically enable the same gate yet produce different
selector support: their different instruction counts change R between reads.
The complete routine model preserves that effect.

In particular, optional rooms cannot occur on a first visit with the raw-bank
harder shortcut, but they **can** on the harder-flag path in B–D. The earlier
entry-only two-visit reduction was rejected by original-ROM replay and must
not be used for those settings. The source retains `allocate()` as a tested
special case; production analysis uses `allocate_three()` for all cases.

## Resource reduction

The ROM makes three visits to twelve ordinary groups, with a fixed descending
thirteenth group keeping the dragon last. Each group has its own three-bit
variant history; optional rooms share five one-use flags. Ordinary choices
consume one history bit. An optional choice consumes one shared flag and leaves
that group's history unchanged.

Fix U and V, the optional-room flags used after visits one and two. U is a
subset of V. Process a group's three selections together with three ordered
resource streams starting at 0, U and V. Require the first stream to end at U
and the second to end at V. Retain each stream's order across groups and the
actual joint selector transitions. This moves only independent work across
groups; it never reorders decisions sharing a resource stream.

The per-group reward is the sum of the three selected room potentials. First
visits retain the normal/harder progress threshold; later visits are harder.
There are only 3^5 possible pairs U subset V. The audited cases require at most
24 live DP states per layer. Six original small-game tests compare this join
with independent chronological exhaustive DAG solving, including optional
rooms on first visits, lexicographic costs and shared-resource boundaries.

The result has two lexicographic components, not only a primary bound. It
saves every selected room, history mask and explicit selector phase. A fixed
already-loaded first variant can be imposed with `--initial-choice 0/1/2`.
`--reuse-selectors` reuses fingerprinted native transducers and repeats the
chronological witness audits; it does not learn transitions from gameplay.

## Attained primary bounds

These values first come from the relaxation allowing every supported selector-entry
refresh phase at each boundary. Independent winning original-CPU executions
attain every primary endpoint below, closing the gap to actual one-life optima.
No probability estimates or guarantee on every random room order is required.

| Revision | Operator | Fewest-input bound | Maximum-score bound |
| --- | --- | ---: | ---: |
| A | 0/1 | 173 | 377011 |
| A | 2 | 185 | 365156 |
| A | 3 | 179 | 365156 |
| B/C/D | 0/1 | 173 | 377011 |
| B/C/D | 2 | 179 | 365651 |
| B/C/D | 3 | 177 | 365156 |
| E/F | 0/1 | 197 | 326248 |
| E/F | 2 | 197 | 326619 |
| E/F | 3 | 191 | 326619 |

The objectives in each row are separate strategies. For example, the A–D
level-zero minimum uses 173 inputs and scores 287442; the maximum uses 215
inputs and scores 377011. E/F have no optional-room injection under supported
banks; their resource join reduces to independent first-variant/version costs.

## Physical attainment and retained reusable tools

`proof-inputs/us-selectors.json` holds complete support and descriptor data.
The original CPU audit checks these data against every logical group,
normal/harder path and refresh class. ROM difficulty progression is audited
separately: the first 0/0/4/8 groups use normal versions at levels 0/1/2/3;
subsequent selections use the harder version. The active room-exit proof
checks the common suffix that preserves cost-plus-future rankings.

`proof-inputs/attaining-plays.json` contains all fifty original classic-board
physical schedules, including all 48 US revision/operator/objective cases.
The two DLE21 cases use the same replay mechanism. Each embedded UTF-8 schedule
retains its original SHA-256; it is never replaced with only a sampled table.
`optimality.py` checks its primary result against a freshly recomputed support
bound and the original successful ROM handler.

`future_roms/search_us_allocations.py`, `future_roms/us_timing_witness.py` and
`future_roms/late_witness_schedule.py` remain available for constructing physical witnesses
for other revisions. A bounded search failure is inconclusive. It must not be
reported as an impossible ROM branch or as proof that an inferior policy is
optimal. None of those tools supplies a runtime fallback.

Current selected-policy min/max results are in
`android/moves/verification/one-life-ranges.json`. US intervals are support
enclosures apart from their attained primary endpoints; do not assume every
other interval endpoint is jointly attainable. Arbitrary post-death continuation
optimality remains outside the requested one-life scope.
