# Whole-game decision-DAG optimization

`rom_proof.py` solves the reduced whole-game models with a backward pass.
`sae_optimality.py` uses the same DAG validation and backward evaluation.
DLE21, US DL1 A–F, A3, SAE, European and Italian proof models share the solver.
DL2 is excluded.

## Reduction and retained information

1. Retain the original record graph for ROM audits and coverage. A state already
   includes the scheduler context established by its ROM model.
2. Find states that have some path to a successful boundary. All others have
   no surviving completion and receive `None`, including closed automatic loops
   and paths feeding those loops. Their rewards are not available on a finish.
3. Topologically order the surviving graph. Any remaining cycle fails with an
   error: neither a free waiting cycle with an input exit nor a score-producing
   cycle is assumed harmless or silently broken.
4. Collapse chains with one action, no input and one destination. Each compressed
   edge retains the sum of skipped awards and its already-resolved destination
   context. Automatic branches stay explicit, so no probability or branch is
   lost. Deaths and goals retain their distinct semantics.
5. Evaluate both objectives and lexicographic tie-breaks in a backward pass.
   Expand values back to every original record, including automatic records,
   and independently check exact Bellman equalities on the original edges.

Both complete ranked alternative lists remain available at every original
state. Alternate player inputs therefore retain their continuation values.
Compression does not replace coverage with a sampled winning path.

The solver computes branch-wise optimistic bounds when Nature has unequal
outcomes. It does not calculate expectations without a probability model.
Existing A3 equality checks and SAE conditional-endpoint checks remain in use.
Scheduler invariants and physical attainment are checked separately by
`audit_schedulers.py` and `optimality.py`.

## Reproduce using little RAM

```bash
python3 tools/offline-moves/test_rom_proof.py
python3 tools/offline-moves/test_sae_optimality.py
python3 tools/offline-moves/verify_cost_runtime.py \
  --roms /path/to/roms
```

Supply the eleven supported DL1/Ace ZIPs; no DL2 ROM is read. Checks are
sequential, use no media and do not launch Android or build APKs. Original-ROM boundary audits run through `audit_schedulers.py --board space-ace`.
These bounded routine audits are distinct from full play/replay timing checks.

The production bundle is checked against every saved independent Bellman
certificate by `verify_cost_runtime.py`. Supplying ROMs also authenticates the
underlying inventories and contextual graphs. Current attained primary bounds
and delivery matrices are indexed in
[`cost-future-summary.json`](../../android/moves/verification/cost-future-summary.json).

## Scope

The production cost-plus-future source bundle uses these complete graphs and
independent Bellman checks. See [COST-FUTURE.md](COST-FUTURE.md) for its current
commands, scheduler audits and physical attainment checks. The old local-search
exporter and bundles have been removed. Bounded CPU-state witness tools remain
available for new ROMs whose abstract support bounds need execution witnesses.
