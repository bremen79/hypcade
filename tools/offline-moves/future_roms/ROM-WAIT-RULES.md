# Accepted-input waits and refresh-phase constraints

`rom_wait_rules.py` transcribes the accepted-input wait gate and its polling
loop directly from the original Cinematronics programs. `rom_phase_audit.py`
observes three naturally reached physical schedules with a copied host Z80
instruction callback. Production sources and the ROM files are unchanged.

```bash
python3 tools/offline-moves/future_roms/rom_wait_rules.py \
  --roms /path/to/rom-zips --output local-tools/wait-rules
python3 tools/offline-moves/future_roms/rom_timer_rules.py \
  --roms /path/to/rom-zips --output local-tools/timer-rules
python3 tools/offline-moves/future_roms/rom_poll_rules.py \
  --roms /path/to/rom-zips --output local-tools/poll-rules
python3 tools/offline-moves/future_roms/rom_phase_audit.py \
  --rom /path/to/lair_d.zip --game lair_d --policy /path/to/shortest.policy \
  --output local-tools/phase-paths --scene 53 --step 7
```

## Literal gate

The accepted descriptor must have header bit 4. Its selected **outcome index**,
not its window number, selects a bit in the extra byte:

| Outcome index | Required extra-byte bit |
| --- | --- |
| 0 | 7 |
| 1 | 6 |
| 2 or 3 | 5 |

If that bit is set, the main CPU waits until all four remaining delay/window
bytes are zero. SAE adds score restoration before rejoining this same gate;
the native audit retains that patch. Ignored FF outcomes and zero-duration
windows are excluded from accepted actions. Remaining later windows must not
be erased when classifying a wait.

## Exact uninterrupted-loop lemma

One iteration loads zero, compares timer bytes in order and branches back at
the first nonzero byte. An indexed comparison takes two M1 fetches and its
branch one. Thus:

| First nonzero byte | M1 increments of R | Parity |
| --- | ---: | --- |
| Delay, offset 12 | 4 | Preserved |
| Window 0, offset 13 | 7 | Flipped |
| Window 1, offset 14 | 10 | Preserved |
| Window 2, offset 15 | 13 | Flipped |
| All zero: leave the loop | 13 | Flipped |

This is an inter-interrupt rule. IRQ execution and timer changes compose with
it; they cannot be assumed to have zero or constant refresh cost.

The original-CPU finite audit passes **45999 cases across all nine Cine ROMs**:
all nonzero byte values, first-active positions, exact timer read sets, refresh
wrap cases, every extra-byte value/outcome index and both header-flag states.
Later timer bytes are proved irrelevant to an individual iteration by checking
that they are not read. The literal instruction signature contains no R write
or read, so the increment formula does not depend on the initial R value.
Generation takes about ten seconds and 38 MiB Python RSS on this laptop.

## IRQ timer potential

`rom_timer_rules.py` transcribes the complete timer-update block, checks its
literal opcodes and register-copy/subtraction helpers, and audits its exact RAM
read/write set. A descriptor decrements only its first nonzero timer byte per
tick. The footer is a saturating 16-bit countdown.

For a fixed list of `n` descriptors, let
`Phi = sum(-21*delay - 14*window0 - 6*window1 + 2*window2)` over the descriptors.
For `N` timer updates without loading or resetting a descriptor:

```
refresh increment = N*(46 + 42*n) + Phi(before) - Phi(after)
                    - 3*min(N, initial_footer)                 (mod 128)
```

Advancing each four-byte timer chain requires four bounded arithmetic steps,
independently of `N`. The original CPU passes **47700 cases across all nine
Cine programs**, including byte/carry boundaries, all descriptor counts 0–16,
active slots, and sequential-versus-bulk composition. Generation takes about
12 seconds and 23 MiB Python RSS. This proves the timer block's refresh effect;
it does not remove other IRQ work or provide the whole IRQ's T-state count.

For a parity-only selector constraint this reduces further: the baseline and
all three window coefficients are even, so the timer contribution modulo two
is `sum(delay_before - delay_after) - min(N, initial_footer)`. This is an exact
consequence of the full refresh formula. It does not assign a parity to the
other IRQ or interrupted main-loop work.

## Released-input polling transfer

`rom_poll_rules.py` summarizes a complete main-thread polling iteration when
physical controls are released, their edge latches are cleared, the footer is
not expired, and service/end branches are absent. Its descriptor contributions
are additive and independent of descriptor order:

| Descriptor state | M1 fetches | T-states |
| --- | ---: | ---: |
| Delay positive | 27 | 199 |
| First window positive | 39 | 297 |
| Second window positive | 48 | 349 |
| Third window positive | 57 | 401 |
| All timers zero, `w` windows | `28 + 9*w` | `211 + 52*w` |

Add the revision-specific base and the checked footer branch costs. For US
DL1/DLE with footer 1–255, the base is 248 fetches/2080 T-states; a nonzero high
byte uses 245/2051. Footer effect bit 0 adds 6/62. A3 and SAE have distinct
low-byte paths, retained separately. A3 reads its footer expiry cutoff from
A016; reaching that cutoff leaves this repeating-transfer domain. The cutoff
audit checks every other byte value, rather than assuming it stays zero.

The native audit passes **146352 cases**. Every case also executes a second
iteration and verifies an exact fixed point for the full CPU structure except
R and for the entire RAM, as well as identical fetch and T-state counts.
Thus, after one normalizing iteration, additional unchanged iterations can be
composed arithmetically. `PollCost.fit()` bounds the number that fit before the
next IRQ or input event; a residual partial iteration still requires exact
instruction execution. This is a primitive for a reduced timing model, not an
implemented whole-game emulator accelerator. The audit takes about 32 seconds
and 23 MiB Python RSS, with no CPU-state graph or random timing sweep.

## Sound and IRQ composition

`rom_sound_rules.py` models the four sound programs as finite pointer/countdown
transitions. With no intervening main-thread writes, N countdown/sequencer
pairs have refresh increment `8*N + Phi(before) - Phi(after)` modulo 128.
Starting a sound is an explicit state/potential change. Pointer low/high and
active-flag writes are separate operations, so a composition cannot assume
that a start is atomic.

`rom_irq_rules.py`, `rom_irq_body_rules.py` and `rom_late_irq_rules.py` retain
revision-specific prefix, timer, handler and sound effects. Instruction-fetch
costs must be composed with the actual RAM transfer and IRQ entry state.
A released-poll arithmetic contract holds only until its earliest input,
interrupt, player event or ROM-state change. A residual partial iteration
requires original-CPU execution.

`rom_phase_classes.py` computes finite clock/refresh residues from proved loop
costs. `rom_frontier_classes.py` binds those arithmetic classes to a decoded
input region. These classes are conditional contracts: a caller still needs
an accepted physical input interval, a fixed polling regime and the actual
path to the selector. Failing to cover every refresh residue does not prove
an inferior game policy optimal.

## Native observations and scope

`rom_phase_audit.py` observes instruction, input, timer, sound and IRQ paths
in a copied host CPU while preserving the ROM and production timing. It uses
bounded observations rather than building a complete CPU-state graph. The
native `fast_rom_poll.c` and `fast_rom_wait.c` primitives require a shadow
original-CPU iteration to establish their skipping preconditions.

These optional tools support future ROM investigation. They are not needed by
the current policy generator or one-life proofs. Current primary support bounds
are closed by independent original-ROM attaining plays through
`../optimality.py`, rather than by assuming that arbitrary refresh phases can
be chosen independently. Current commands and evidence are documented in
[the production guide](../COST-FUTURE.md).
