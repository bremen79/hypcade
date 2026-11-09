#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regenerate conservative move signatures from user-owned ROMs (never copies ROMs).
Requires a local laser-vault Git checkout, a C compiler and zlib development files.
The oracle runs on the build computer, never on the Android arcade machine.
"""
import argparse
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile

REVISION = "1f12c84dfabf3c8e5d028c8804b2f96678c798fa"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--oracle", type=Path, required=True)
parser.add_argument("--roms", type=Path, required=True)
parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "app/jni/arcade_moves.inc")
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix="hypseus-move-oracle-") as temporary:
    root = Path(temporary)
    archive = subprocess.check_output(["git", "-C", str(args.oracle), "archive", REVISION, "src"])
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar:
            path = root / member.name
            if not member.isfile() or ".." in Path(member.name).parts or Path(member.name).is_absolute():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(tar.extractfile(member).read())
    trace = root / "src/tools/cine_trace.c"
    text = trace.read_text().replace('    ldp_init(&ldp, DISC_FPS, 0);', '''    if (strstr(roms, "dle21")) memset(board.rom + 0x6000, 0, 0x4000);
    ldp_init(&ldp, DISC_FPS, 0);''')
    trace.write_text(text)
    source = root / "src/games/cinematronics/autoplay.c"
    text = source.read_text()
    assert text.count('        ap->moves_made++;') == 1
    text = text.replace('        ap->moves_made++;', '''        {
            uint64_t hash = UINT64_C(14695981039346656037);
            for (int e = 0; e < 16; ++e) {
                const uint8_t *entry = board->ram + 0xe0 + e * 16;
                if (!(entry[0] & 0x80)) break;
                for (int k = 0; k < 12; ++k) { hash ^= entry[k]; hash *= UINT64_C(1099511628211); }
            }
            CineMove observed[16];
            int count = cine_open_moves(board, observed, 16);
            for (int k = 0; k < count; ++k) if (observed[k].input == input)
                printf("ASSIST %016llx %u %u %d\\n", (unsigned long long)hash, observed[k].outcome, input, ldp->frame);
        }
        ap->moves_made++;''')
    source.write_text(text)
    sources = ["tools/cine_trace.c", "games/cinematronics/board.c", "games/cinematronics/autoplay.c",
               "cpu/z80.c", "ldp/ldp.c", "ldp/ldv1000.c", "util/roms.c", "util/zip.c", "audio/ay8910.c"]
    binary = root / "oracle"
    subprocess.run(["cc", "-O3", "-std=c11", "-D_POSIX_C_SOURCE=200809L", "-I" + str(root / "src"),
                    *[str(root / "src" / name) for name in sources], "-lz", "-lm", "-o", str(binary)], check=True)
    output = "// SPDX-License-Identifier: GPL-3.0-or-later\n// Observed safe outcomes: move-header hashes and disc-frame context; no ROM bytes.\n"
    for game, settings in [("dle21", ["--dsw1", "30", "--press", "start1@68"]),
                           ("ace", ["--press", "coin1@65", "--press", "coin1@66", "--press", "start1@68", "--press", "ace@69"])]:
        result = subprocess.check_output([str(binary), str(args.roms.resolve() / (game + ".zip")),
                                          "--seconds", "1500", *settings, "--autoplay"], text=True)
        observations = set()
        for line in result.splitlines():
            if line.startswith("ASSIST "):
                _, key, outcome, control, frame = line.split()
                observations.add((int(key, 16), int(outcome), int(frame)))
        if not observations:
            raise RuntimeError("No verified observations for " + game)
        print(game, len(observations), "observations")
        output += "static const SafeOutcome " + game + "_moves[] = {\n"
        for key, outcome, frame in sorted(observations):
            output += f"    {{UINT64_C(0x{key:016x}), {outcome}, {frame}}},\n"
        output += "};\n"
    args.output.write_text(output)
