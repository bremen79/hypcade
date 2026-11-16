# Offline arcade strategy tools

The production generator calculates scene cost plus the remaining-game cost of
the chosen exit. It supports DLE21, US Dragon’s Lair A–F, Space Ace A3, SAE 1.0,
European Dragon’s Lair and the Italian revision. DL2 uses its own ROM prompts.
Commercial ROMs and media are not included or packaged in the APK.

See [COST-FUTURE.md](COST-FUTURE.md) for generation, proof checks, publication
and the retained tools for extending the method to other ROMs. The older
local-search exporter, bundle merger and matrix-building workflow are removed.

```bash
python3 tools/offline-moves/cost_runtime.py \
  --roms /path/to/roms --output local-tools/cost-future-candidate
python3 tools/offline-moves/verify_cost_runtime.py \
  --bundle-dir local-tools/cost-future-candidate --roms /path/to/roms
python3 android/tests/test_bundled_moves.py --roms /path/to/roms
```

The first two commands check a candidate. The last checks the production source
bundle and its JNI includes. Do not replace production includes until candidate
proof and delivery checks pass. Python 3.9+ is required; native original-CPU
checks additionally need a C11 compiler and zlib development headers. No video
files, real-time waits, Android SDK or Android emulator are needed for host
ROM generation and proof checks.

Use the ROM ZIP names `dle21`, `lair_a` through `lair_f`, `ace`, `sae`,
`laireuro` and `lair_ita`. A split Italian ZIP needs its adjacent European parent.
The decoder verifies chip names, sizes and CRCs; it rejects unknown revisions.
Keep ROMs and temporary results under visible `local-tools/` directories.

## Verification scope

Fewest moves and Max score optimize the possibility of attaining their primary
extreme in a surviving initial game. No probability estimates are needed. Only
cardinal directions and the action button are allowed. Global continuation
optimality after arbitrary mistakes/deaths is outside the current requested
scope. Every decoded rule and ranked surviving alternative remains in the
source audit, including branches not visited in any sampled play.

Runtime policies store priorities and descriptor identities. The running ROM
supplies its current timing windows and difficulty adjustments. A required
zero-score action must be retained. Sampling cannot define table coverage, and
a relaxed graph endpoint needs physical attainment before it proves an optimum.

[WATCH-VERIFY.md](WATCH-VERIFY.md) distinguishes original-CPU physical replay,
modeled input delivery and the Java/JNI host harness from Android runtime tests.
Use one native worker for modest CPU use; each video-less machine uses little
RAM. Current build, matrix and installed-APK results are maintained in
[the validation guide](../../android/VALIDATION.md), with their source
fingerprints and scope limitations.

Optional tools for other ROMs, their tests, native helpers and timing notes are
in [future_roms/](future_roms/README.md). They are not dependencies of the current
generator, proof checks or runtime validation.

## ROM rules and reusable analysis

* [ROM record layouts](ROM-EXPORT.md)
* [Decision-DAG reduction and Bellman verification](DAG-OPTIMIZER.md)
* [Executable SAE rules](SAE-RULES.md)
* [US selector allocation](US-DL1-ALLOCATION.md)
* [DLE21 scheduler certificate](DLE-SCHEDULER.md)
* [Current criteria, composition and reusable tools](COST-FUTURE.md)

The original CPU/player subset is from Jeff Nyman’s GPL-3.0-or-later
laser-vault, pinned at `1f12c84dfabf3c8e5d028c8804b2f96678c798fa`.
Preserve its source notices and provenance in `vendor/`. Android additions
retain their GPL-3.0-or-later notices.
