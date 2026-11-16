# Cost plus continuation: production strategy tools

The production source bundle is `android/moves/strategies/`. Its two includes
are copied to `android/app/jni/arcade_moves.inc` and `arcade_euro_moves.inc`.
The APK compiles their ranked rules and indices. Decoded inventories, graphs,
Bellman certificates and physical proof inputs stay in the source tree; none
of those files is an APK asset. Timing comes from the running ROM's loaded
input descriptors, including its current skill and difficulty adjustments.

## Criteria

Optimize a surviving, one-life initial game. Fewest moves must have a
physically attainable path with the smallest accepted-input count; Max score
must have one with the highest score. Do not estimate probabilities or optimize
expected values. Only cardinal directions and the action button are allowed.
Keep every ranked surviving alternative, necessary zero-score actions and
the decoded audit records for excluded/death/ignored windows. Sampling must
never define runtime coverage. Functional recovery tests do not establish
global optimality after arbitrary mistakes or deaths.

## Rebuild and check

From the repository root, with your own CRC-validated ROM ZIPs:

```bash
python3 tools/offline-moves/cost_runtime.py \
  --roms /path/to/roms --output local-tools/cost-future-candidate
python3 tools/offline-moves/verify_cost_runtime.py \
  --bundle-dir local-tools/cost-future-candidate --roms /path/to/roms
python3 tools/offline-moves/audit_schedulers.py \
  --roms /path/to/roms --output local-tools/scheduler-audit
python3 tools/offline-moves/optimality.py \
  --bundle local-tools/cost-future-candidate --roms /path/to/roms \
  --output local-tools/optimality --replay-classic
```

The first command calculates scene-local input/reward costs plus each chosen
exit's remaining-game cost. Independent backward DAG solves check all four
objective/tie-break value arrays. US DL1, DLE21 and European room rankings have
a common future offset: ROM scheduler contracts establish when that offset
cancels. A3 retains skill/replay context; SAE retains score suppression and
exact descriptor identity. The shared runtime key is checked against all
generated contexts, rather than only a winning route.

`verify_cost_runtime.py --roms` reconstructs the complete ROM inventories and
context graphs. Without ROMs it checks saved Bellman certificates, every ranked
alternative and source/output fingerprints. `android/tests/test_bundled_moves.py`
is the build gate and also requires the production includes to match the bundle.
Its `--apk FILE` option checks that each native library contains the expected
rule pools and strategy indices.

`audit_schedulers.py` executes bounded original-CPU routine tests: complete US
selector support, difficulty progression, fixed rewards and group advancement;
DLE21's authored macro scheduler; European/Italian queue contracts. Room-order
permutations do not need their own graph. `optimality.py` independently composes
86 Cine initial objective bounds and replays all 50 classic-board winning
physical schedules. A relaxed support bound needs an attaining original-ROM
execution before it establishes an attainable optimum. European optimal
policies apply to every already constructed queue; Italian pool enclosures
are not claims of joint RNG attainability.

Use [WATCH-VERIFY.md](WATCH-VERIFY.md) for production-selector timing tests.
The host Cine checker records actual input delivery and CPU advances, then
replays them in a fresh process without choosing actions from a policy. Check
Space Ace's accepted-command count, not the number of attempted pulses. The
Euro checker additionally uses the production Java controller and JNI publisher.
Neither host check is an Android emulator or physical-device validation.

After candidate checks pass, replace the source bundle and both JNI includes
together. Do not copy timings from a witness or publish only its visited rows.
Build, delivery-matrix and installed-APK results are maintained in
[`android/VALIDATION.md`](../../android/VALIDATION.md). Keep measurements and
validation scope there rather than duplicating them in this generation guide.

`verify_euro_watch.py --android SERIAL` runs the same Java/JNI matrix on an
already running x86 emulator. It cross-compiles the native harness for API 25
and runs the controller under Android ART. Its relocated test Handler keeps
the clock deterministic; this is an accelerated harness test, separate from
an installed-APK play with the real Android Handler.

## Retained tools for other ROMs

Current generation and proof dependencies remain in this directory. Optional
analysis for new ROMs is isolated in [future_roms/](future_roms/README.md),
including its 21 Python modules, sixteen test modules, three native helpers and
timing reference. Production tools do not import that package.

| Location | Purpose |
| --- | --- |
| `rom_tables.py`, `euro_tables.py`, `rom_controls.py` | Revision/CRC validation, inventories, accepted regions and cardinal control reduction |
| `rom_rules.py`, `ace_rules.py`, `sae_rules.py`, `cine_recovery_model.py` | Current source-addressed transitions, rewards and context models |
| `rom_proof.py`, `scene_strategies.py`, `dl1_exit_strategies.py` | Current DAG validation, Bellman values and local/exit cost composition |
| `rom_kernel.c` / `.py`, `vendor/`, `simulation.c`, `board_adapter.c` | Shared original CPU/player and bounded routine-call audits |
| `optimality.py`, `audit_schedulers.py`, `verify_*watch.py`, `verify_euro_global.py` | Current optimality, original-ROM and delivery validation |
| `proof-inputs/` | Embedded/checksummed original-CPU winning schedules and scheduler certificates |
| `future_roms/` | Optional stochastic/support solvers, timing/IRQ/refresh arithmetic, witness construction, bounded CPU search and disassembly |

The older local-search exporter, matrix builder, bundler and merger have been
removed. Shared decoding, original-CPU player compilation and graph/control
analysis remain as libraries used by the current strategy and proof tools.

New revisions need their own validated layouts and scheduler contracts.
Retain original ROM transitions and rewards; collapse only contexts whose
objective-relevant future is proved equivalent. Reject a surviving cycle or
an unresolved destination instead of assuming the new game has the same DAG.

## Why the proof is sufficient

The ROM models retain each action's accepted-input cost, record reward and
future context. Independent Bellman checks cover every saved state and branch.
The context compression must preserve each complete ranking. A ROM execution
therefore cannot obtain a lower input count or larger score than its relaxed
support bound. For both objectives, original-CPU physical replay then attains
the relevant bound, establishing the requested one-life optimum. Room queues
or permutations with the same additive costs need no explicit order graph.

Per-scene calculation consumes only that scene and its already solved exits:
remaining inputs/score equal local inputs/score plus the chosen exit's value.
Whole-game backward solves check all four objective/tie-break arrays separately.
Waiting costs zero inputs but retains any intervening rewards. A surviving cycle
or unresolved target is an error; a closed automatic loop supplies no winning
continuation.

The current scope and all 102 min/max results are recorded in
`android/moves/verification/one-life-ranges.json`. Italian policies are optimal
for each ROM-created queue; queue-conditioned totals and pool-wide enclosures
must remain distinct from proved joint RNG endpoints. Functional recovery
checks do not establish optimality after arbitrary mistakes/deaths.

Older range exporters, report aggregators, obsolete timing experiments and
deferred recovery-policy experiments have been removed. General ROM timing,
refresh-class arithmetic, CPU execution and graph tools remain available for
new revisions. Exact proof schedules are embedded in `attaining-plays.json`;
they are written as temporary individual traces only when replaying them.
