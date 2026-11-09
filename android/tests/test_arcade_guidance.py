#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Host regression checks for the production move-window decoder."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="hypseus-guidance-") as tmp:
    binary = Path(tmp) / "guidance-test"
    subprocess.run(["c++", "-std=c++11", "-Wall", "-Wextra", "-Werror",
                    "-DHYPSEUS_GUIDANCE_HOST_TEST", "-I" + str(root / "android/app/jni"),
                    str(root / "android/tests/arcade_guidance_test.cpp"),
                    str(root / "android/app/jni/arcade_guidance.cpp"), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
