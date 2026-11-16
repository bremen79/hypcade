# DLE21 authored scheduler certificate

`dle_scheduler_graph.py` composes the ROM's complete room-exit graphs with the
original selector's variant-history transitions. Its **412 macro states** keep
consumed variant bits, not permutations of completed rooms. The graph includes
all surviving room exits and all three final-chapter choices.

```bash
python3 tools/offline-moves/verify_dle_rules.py \
  --rom /path/to/dle21.zip --output local-tools/dle-rules
python3 tools/offline-moves/dle_scheduler_graph.py \
  --rom /path/to/dle21.zip --selector local-tools/dle-rules/report.json \
  --output local-tools/dle-scheduler/certificate.json
```

The finite selector audit executes **159744 original-CPU cases** across every
valid descriptor history, all 128 refresh seeds, both player RAM slots, both
harder-flag states and normal/retry entry. It starts at the complete 1CC3 entry.
Direct-room descriptors leave their histories unchanged. Entering at 1D50 skips that branch and cannot supply the current state transitions.
Retry/player branches can shift R before selection, so identical input refresh
seeds are not assumed to produce identical rooms. Exact support is checked.
Factory A011.7 bypasses the harder-table offset even when progress sets the
harder flag. The actual authored normal roots must therefore be used. Histories
outside a descriptor's mask are not valid initial states; they manufacture
out-of-table roots and are rejected from the semantic domain.

For each possible room exit, the local DAG computes all four conditional
potentials. The scheduler then composes those costs with the next macro state.
Every Nature alternative has identical continuation values at every macro
state. Every successful exit of a room has the same suffix value, including
the hub's three final chapters. The final chapters contain the same nine-room
multiset with the dragon last. Necessary mirror pairs agree on all four
lexicographic values. Thus changing refresh phase or scene permutation cannot
improve these fresh-game bounds; no probability law or phase-steering witness
is needed here.

The certificate also has an independent numerical checker: it checks every
Nature branch's Bellman equality, common exit costs, acyclicity and the initial
bridge prefix. Its original small-game counterexamples reject an unequal
Nature branch, a wrong secondary value, a zero-cost cycle and a missing prefix.

| Strategy | Inputs | Score |
| --- | ---: | ---: |
| Fewest inputs, score tie-break | **147** | **314457** |
| Maximum score, input tie-break | **155** | **333333** |

Both original-ROM plays independently replay with their complete physical
input traces and attain both components. `verify_cine_end.py` additionally
observes the genuine successful ROM handler at 158C with the winning footer
and frame 30744. The handler can occur during the final replay checkpoint, so
observing only a later no-input continuation is insufficient. Counterfactual
copies are excluded from the observer, and synthetic negative tests reject a
wrong frame, a death footer and an operand read in place of an opcode fetch.

For example:

```bash
python3 tools/offline-moves/verify_cine_end.py \
  --rom /path/to/dle21.zip --game dle21 --trace /path/to/shortest.trace \
  --output local-tools/dle-end-replay
```

The shared-suffix property proves local ranking agreement for every surviving
record within these fresh-game macro contexts, including alternate accepted
inputs. Adding the suffix changes values but does not change either policy.
The existing local strategies therefore need no route correction for DLE21.

## Current proof inputs and scope

The fifty classic-board physical witnesses, including both DLE objectives,
are stored verbatim with checksums in `proof-inputs/attaining-plays.json`.
`optimality.py --replay-classic` materializes each schedule only in its output
folder, then independently replays it and observes the original successful end.
`audit_schedulers.py` freshly reconstructs the 412-state scheduler from the
original CPU's selector support and compares every saved semantic value.

The current requested optimum concerns surviving initial games. Functional
life-loss recovery is checked by the bundled-selector Watch matrix. Optimal
continuation after arbitrary deaths is outside that proof scope. The shared
ROM/CPU/graph primitives remain available for further revisions.
