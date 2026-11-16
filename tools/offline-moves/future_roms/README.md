# Optional tools for future ROMs

These tools are retained for new ROM investigations. The current production
generator, proof checks and runtime validation use the parent directory and
have no dependencies on this package. Shared ROM decoders, the original CPU
kernel/player and vendor sources remain in that parent directory.

| Tools | Purpose |
| --- | --- |
| `game_graph.py`, `possible_strategies.py`, `control_bounds.py` | Generic stochastic/support objectives and policy-value bounds |
| `rom_*_rules.py`, `rom_phase_classes.py`, `rom_frontier_classes.py`, `rom_phase_audit.py`, `verify_rom_phase_classes.py` | Input timing, IRQ/sound/timer effects and finite refresh-class analysis |
| `dl1_continuation_costs.py`, `dl1_prefix_costs.py`, `search_us_allocations.py`, `us_timing_witness.py`, `late_witness_schedule.py` | Conditional selector allocations and physical witness construction |
| `whole_game.py` / `.c` | Bounded original-CPU checkpoint search when a new model needs execution witnesses |
| `fast_rom_poll.c`, `fast_rom_wait.c` | Experimental low-level loop batching primitives requiring a caller |
| `z80_listing.py` | Diagnostic Z80 disassembly |
| `test_*.py` | Focused tests of these optional components |

Commands can still run directly, from any working directory:

```bash
python3 tools/offline-moves/future_roms/z80_listing.py --help
python3 tools/offline-moves/future_roms/rom_phase_audit.py --help
```

From `tools/offline-moves/`, package imports also work:

```python
from future_roms import game_graph, possible_strategies
```

Run core and optional tests together from the repository root:

```bash
python3 -m unittest discover -s tools/offline-moves -p 'test_*.py'
```

Only bounded native checks and small fixtures are used by these tests; they do
not launch Android. Actual ROM analysis commands can have larger work budgets;
inspect their options and resource budgets first.
[ROM-WAIT-RULES.md](ROM-WAIT-RULES.md) documents the
optional timing models and their explicit preconditions. Statistical solvers
here are not part of the current attainable-extreme objectives.
