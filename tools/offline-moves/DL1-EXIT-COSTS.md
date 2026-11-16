# DL1 local strategies with explicit exit coefficients

`dl1_exit_strategies.py` calculates, for every decoded decision-graph state,
the optimal local cost **to each semantic exit separately**. Both objectives
retain their tie-break: Fewest moves maximizes score among minimum-input
paths; Max score minimizes inputs among maximum-score paths.

For an exit `e`, the caller supplies its remaining-game values. The complete
cost is the saved local value to `e` plus the supplied continuation value.
`evaluate()` chooses the best resulting value and `ranked()` ranks all safe
local alternatives. Missing exit costs fail explicitly; four explicit `None`
values mark a known exit with no surviving continuation. Local transitions
with several destinations require a separate probability/phase contract and
are rejected; no stochastic distribution is invented.

The exit value must be valid for every internal path to that exit. In
particular, a semantic `next` exit does not identify a physical CPU refresh
phase. The coefficient tables do not solve that timing dependency.

## Saved tables and independent checks

```bash
python3 tools/offline-moves/dl1_exit_strategies.py \
  --roms /path/to/roms \
  --output local-tools/dl1-exit-values
```

The nine `*-exit-values.json` files cover DLE21, US A–F, European and Italian
Dragon's Lair. They save every graph record, per-exit local values, all retained
action alternatives and their per-exit values, explicit no-safe-completion
states, and the zero-future comparison with the original local optimizer.
They also record controls excluded by the independently checked cardinal-input
reduction and the complete ROM-inventory fingerprint. Timing comes from live
ROM scene/step descriptors or European record IDs; no calibrated frames are
introduced.

These are offline coefficient/audit files, explicitly `runtime_ready: false`.
They are not an APK bundle or a replacement for the complete decoded rule
inventory. The graph covers record closures from the existing ROM models,
including decoded aliases; it is not a claim that every alias is naturally
selected by the supported game configuration.

All **8,954 states** pass four-value checks, 35,816 checks in total. The
independent reference appends actual input/reward paths after every exit,
solves that extended game, and compares all original states. This tests exit
costs with different primary and secondary objectives without feeding the
reference solution to the coefficient calculation. Seven unit tests additionally
cover exit-dependent choices, common offsets, terminal rewards, off-policy
states, unsafe paths and missing/probabilistic contracts.

Zero future values reproduce the existing local optimizer without primary or
secondary losses for any of the nine ROMs. This is a scene-boundary comparison,
not an APK binary comparison or unconditional whole-game proof.

## Simplification established by the ROMs

All surviving A–F records have one semantic exit each. The same holds for
European and Italian records. Their future cost is therefore a common offset
within a record and cancels from local action ranking. Where scheduler
invariants make the future independent of path and timing, the original local
ranking already gives the correct whole-game continuation ranking.

DLE21 has 24 decoded records with multiple semantic exits, across scene aliases
20, 21, 71, 72 and 101. The export preserves their separate coefficients.
Some aliases belong to unused version tables. Applying a supported-game
chapter-equivalence reduction requires the separate DLE scheduler contract;
this exporter does not silently identify their exit values.

For the supported A–D difficulty settings, optional-room injection remains
enabled. Its disabling gate is A011 bit 7; changing the difficulty does not
provide the proposed fixed-multiset shortcut. The phase/resource model remains
necessary. Adding one constant per semantic room exit cannot recover the
documented physical timing gains, because all surviving local choices already
share that exit class. A phase-aware exit relation must distinguish the future
states created by different legal input timings.

SAE and A3 retain their separately validated contextual local-plus-exit
generators. DL2 remains excluded. No Android runtime test or APK size gain is
claimed by these offline coefficients.
