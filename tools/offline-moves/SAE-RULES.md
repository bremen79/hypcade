# SAE executable ROM rules

For the regenerated local strategies with explicit exit values and live-ROM
tables, use [COST-FUTURE.md](COST-FUTURE.md). The scene-based and
whole-game solutions agree under both selector conditions.

`verify_sae_rules.py` validates the executable transcription against the
original Z80 and exports typed rules, the complete record graph and a decision
DAG. `verify_sae_timing.py --matrix` then constructs physical input schedules,
independently replays them and checks attainment of the DAG bounds. Both
lexicographic objectives are now certified for all six SAE skill/operator
settings at start delay zero. The production generator consumes these models
to construct the packaged policies; standalone timing exports are audit inputs.

## Rules, DAG and timing

* `rom_rules.py` defines byte-addressed memory, source addresses, input windows,
  rewards, decisions, external observations and explicitly justified rational
  distributions. ROM writes and unmapped accesses fail. Words and bytes wrap
  at their original widths. Queue/history aliases share the same byte store.
* `sae_rules.py` transcribes SAE's queue initialization, outcome application,
  logical dispatch, progress counter, physical selector, checkpoint and life
  restart rules as readable Python. Each rule names its original ROM entry.
  Raw input windows and their header/extra condition fields come from the
  existing CRC-pinned decoder. Unsupported completion/replay effects fail.
* `verify_sae_rules.py` executes the original routines with the small native
  Z80 kernel and compares the complete resulting RAM below the harness stack.
  It also verifies the graph's projections before exporting them.
* `sae_timing.c` / `sae_timing.py` run the original CPU, IRQ, input handling and
  player clocks for any supplied physical input schedule. `SaeRules.timed()`
  binds every actual accepted outcome and refresh read to the readable rules,
  checks every record boundary, and includes automatic death clips and life
  restarts. Two machine slots and a bounded event buffer replace a timing-state
  graph. The caller cannot supply an arbitrary R value to this timed API.

The transcription covers **accepted-outcome and restart boundaries**. It is
not a CPU instruction lifter or a transcription of the video waits, coin/start
sequence, input polling, skill-adjusted timer loader or score-display routine.
Those remain with the original emulator. Exported windows retain the original
condition fields; their physical acceptance is not inferred from graph edges.

## Refresh is an explicit observation

At ROM `1EB1`, the selector reads `R`; at `1EB3`, it masks that value with 1.
The concrete rule requires the value at that read site. If it is missing,
`ObservationRequired` identifies the read rather than inventing a probability.
The native checker observes the original CPU's actual read without changing
execution, including refresh-register wraparound.

The exported decision alternatives include the observed bit and its source
address. `probability_model` is null. `Distribution` and `Decision.expectation`
can express a caller-supplied rational law, but require an explicit justification.
The fact that two outcomes exist never implies weights of one half each.

In particular, input timing can affect this read. Earlier independently replayed
SAE Cadet traces with the same first 59 inputs and the same accepted 60th SHOOT
outcome sampled R=77 versus R=0 after a 4104-cycle press shift. Their final
scores were 318706 and 319498. The timed binding reproduces both complete
151-command plays and every original CPU/player checkpoint. It computes phase
using original CPU execution, rather than an independently decompiled formula.

## Separate timing where the ROM permits it

SAE loads its award from `2 * word(2503 + 2*(footer.flags & 15))` at
`1707–171D`. Its patched award routine (`1BD7 -> 094A`) adds that fixed amount
atomically, subject to the suppression bit at A00A.1. These paths are checked
against the original CPU for all sixteen award ranks and both gate values,
including score-byte carries. The award itself has no early/late multiplier.

The observed timing dependence instead changes a future physical scene through
`LD A,R`. Compare both continuation values at each external branch. Captain
and Ace have equal lexicographic values at every such branch; neither needs a
timing search to attain the initial optimum. Cadet has unequal branch values.
Tracing backward through automatic edges locates just two mirrored last-input
records: scene 13/14, step 18, SHOOT. These are derived from the graph, not from
a sampled successful path. They lead through episode 40's dispatchers.

Solve the timing-relaxed DAG first. Its minimum command count is a lower bound
and maximum score is an upper bound for any legal timed execution. A surviving
physical schedule attaining the bound certifies optimality for that concrete
start. The same comparison certifies the secondary objective. There is no
need to enumerate CPU phases once such a witness exists.

The matrix tries normal ROM-ranked play first, then, only if necessary, delays
inputs at the unequal-branch frontier by a small bounded set of intervals.
The two Cadet maximum-score cases attain the bound with the first 4096-cycle
probe; every other case attains it without a timing probe. Failed probes are
discarded schedules, not policy rows. Finite probing alone is not a proof:
bound attainment and independent replay supply the certificate. Equal relaxed
branch values alone also do not prove timing feasibility from arbitrary states.

## Checked simplifications

The concrete rules retain full RAM history. Only the graph layer simplifies it:

1. Build a conservative macro graph over logical episode, queue cursor and
   actual queue bytes, including every decoded outcome and surviving life
   restart. Verify that no path can select the same logical episode twice.
   A hypothetical first revisit would already appear in this fresh-selector
   graph, so its absence proves that non-aliased histories can be erased.
   Restarting the current room without selecting an episode is not a revisit
   of the selector and does not violate this invariant.
2. Retain the three queue bytes literally. Episode 34's history aliases A082;
   in Ace, it can change raw byte 156 to 158 (logical 28 to 30). No separate
   history map or special correction can disagree with the physical byte.
   Only two queue tuples occur in Ace; the other skills have one each.
3. Verify that every reached record lacks the enabling completion/replay bits.
   The original low-outcome routines then leave routing unchanged under either
   value of the revisit flag. Both values are exercised in boundary checks.
4. Retain the actual checkpoint. Its update is gated by operator-bank bit 7,
   not by skill. The concrete progress counter is still transcribed, including
   byte wraparound and SAE's NOP patch; the graph does not use it as a hidden
   difficulty change or pretend that its instruction cost is modeled.
5. Collapse deterministic automatic chains while retaining their rewards.
   Keep selector observations explicit. Check the entire record graph for
   cycles, including losing branches, and check all four Bellman value arrays
   on original edges after expanding the solution back to original records.

Accidental restart links are exported as a separate coverage relation. They
are not selectable actions for improving the objective. This avoids multiplying
states by remaining lives while still supplying continuations after a death.

## Complete deviation and restart policies

`sae_continuations.py` calculates both policies throughout the ROM-derived
closure, including paths never visited in a successful sample and all restart
targets. The state now includes **A00A.1, score suppression**, in addition to
episode, physical scene/step, queue cursor, checkpoint and aliased queue bytes.
The original death patch sets this bit. Only an accepted descriptor with
header bit 4 clears it. Awards already suppressed at the current load are not
retroactively added. This affects future rewards and can change retry choices.

For example, scene 2 step 17 accepts LEFT to outcome 18 at ticks 6–24 using
header A4, or at ticks 48–66 using header B4. The later descriptor clears score
suppression. A fresh visit can prefer the early window; after a death, the
later window restores subsequent awards. Scene/step and outcome alone would
discard this distinction.

| Skill | Operator 0 contexts | Operator 1 contexts |
| --- | ---: | ---: |
| Cadet | 4591 | 834 |
| Captain | 6099 | 1102 |
| Ace | 8475 | 1498 |

Across these 22599 contexts, 10693 have a surviving completion, 11259 are
death/restart contexts and 647 other contexts have no surviving completion.
The latter receive no invented winning move. Death animations are automatic;
guidance waits for the actual restart. With no life left, it reports game over.
Death is never an action chosen to improve a reward.

The solver retains two conditional value functions for episode 40's refresh
bit. It verifies the **entire move ranking**, including alternatives, is the
same in both conditions at every context. Captain and Ace also have identical
values in both conditions. Cadet's conditional values remain explicit: a shared
move ranking is not an unconditional numerical score or a proof that every
current clock phase can realize either selector outcome.

The executable policy checks descriptor priority and remaining timer bytes.
It removes expired windows, retains future windows, waits for an outstanding
accepted input, and supports the ROM's diagonal controls 5/6/9/10. Complete raw
alternatives remain in the audit. Removing windows unavailable under the tick
rules changes none of the four conditional value arrays at any context.
Native audits check the original loader, IRQ timer arithmetic and causal
acceptance for all 23501 input regions, with simultaneous no-input controls;
there are additionally 19182 IRQ region-boundary checks.

`Continuations.lookup()` accepts a complete ROM context and an optional set of
remaining labels. `lookup_live()` obtains those labels from the timed binding's
actual RAM. Results keep both selector-conditioned values unless a bit is
supplied. Values include the current record's award; subtract `current_award`
when querying just after that award was already published by the loader.

The continuation API retains structural values for alternative and retry
contexts. Its optional recovery/deviation checks bind concrete original-CPU
schedules to those values; they do not establish physical attainability or
optimality at every possible CPU-cycle phase after arbitrary mistakes. These
audit exports are not directly packaged. `cost_runtime.py` generates production
policies from the contextual models, with current validation scope recorded in
[VALIDATION.md](../../android/VALIDATION.md).

```bash
python3 tools/offline-moves/test_sae_continuations.py
python3 tools/offline-moves/sae_continuations.py \
  --rom /path/to/sae.zip --audit-inputs \
  --recovery-matrix --deviation-matrix \
  --output local-tools/sae-continuations
```

SAE's skill byte remains fixed. At `1E0A–1E0B`, SAE NOPs the harder-mode flag
write that A3 performs after its episode threshold. The current SAE rules
preserve that patch. A3's changing difficulty is a separate model obligation.

## Reproduce with little RAM

```bash
python3 tools/offline-moves/test_sae_rules.py
python3 tools/offline-moves/test_rom_kernel.py
python3 tools/offline-moves/test_sae_timing.py
python3 tools/offline-moves/verify_sae_rules.py \
  --rom /path/to/sae.zip --output local-tools/sae-rules
python3 tools/offline-moves/verify_sae_timing.py \
  --rom /path/to/sae.zip --matrix --negative-controls \
  --output local-tools/sae-strategies
```

No media, network, Android SDK or emulator is needed. Native tools use the
pinned CPU/player sources. Checks run sequentially. The rule output has six
skill/operator JSON artifacts and `report.json`. The strategy output has full
ROM-derived ranked policies, physical schedules, independently replayed timed
edges, actual refresh observations and certificates with source/ROM fingerprints.
The replay checker has no access to a policy, timing probe or survival oracle.
Existing `HYPCADE_ROUTE_V2` schedules can instead be checked with repeated
`--trace /path/to/route.trace`, plus their `--skill`, `--difficulty` and
`--start-delay`. This mode also retains verified timing-relaxed bounds when a
replayed schedule does not attain the optimum.

Each artifact contains source-addressed record metadata, every decoded input
window, decisions with rewards and observed alternatives, separate accidental
recovery links, the full graph, reduced DAG and four value arrays. It contains
no copied ROM instruction payloads. The original-ROM validator uses 25143
isolated-routine cases and 126566 composed boundary/restart cases in the
score-aware closure. Original
synthetic fixtures independently test byte aliases, checkpoint gates, external
reads, explicit probabilities and the native read observer.

These tools run on the host without video or real-time waits. Their timed
bindings check concrete accepted inputs and successful ROM completion against
the decision-DAG values. Current one-life endpoints, conditional ranges and
Android delivery results are maintained in
[VALIDATION.md](../../android/VALIDATION.md) and its linked reports. Do not
interpret a concrete timing certificate as universal attainability after
arbitrary deviations or deaths.

## Current integration scope

`cost_runtime.py` uses this transcription through the complete contextual scene
solver. `verify_cost_runtime.py --roms` reconstructs those graphs and checks all
rankings; `audit_schedulers.py --board space-ace` validates their boundary rules
against the original CPU. A3 and the other boards retain their own validated
adapters. The resulting policies are integrated into the JNI source inputs.
DL2 uses its ROM prompts and remains excluded from this optimization.

The current one-life objectives and reproducible checks are documented in
[COST-FUTURE.md](COST-FUTURE.md). Global optimality after arbitrary mistakes or
deaths remains outside the requested scope.
