#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
"""Run the production Java launcher's model checks using JDK 17, without Android."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jdk", type=Path, help="JDK directory, if java/javac are not on PATH")
    options = parser.parse_args()
    jdk = options.jdk or (Path(os.environ["JAVA_HOME"]) if os.environ.get("JAVA_HOME") else None)
    suffix = ".exe" if os.name == "nt" else ""
    java = str(jdk / "bin" / ("java" + suffix)) if jdk else shutil.which("java")
    javac = str(jdk / "bin" / ("javac" + suffix)) if jdk else shutil.which("javac")
    if not java or not javac:
        parser.error("JDK 17 is required; use --jdk, JAVA_HOME, or add java/javac to PATH")
    root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="hypseus-launcher-test-") as directory:
        compiled = Path(directory) / "classes"
        compiled.mkdir()
        subprocess.run([
            javac, "-encoding", "UTF-8", "-Xlint:all", "-Werror", "-d", str(compiled),
            str(root / "android/app/src/main/java/org/hypseus/android/LaunchConfig.java"),
            str(root / "android/app/src/main/java/org/hypseus/android/MoveMode.java"),
            str(root / "android/app/src/main/java/org/hypseus/android/GameDifficulty.java"),
            str(root / "android/app/src/main/java/org/hypseus/android/GuidanceSupport.java"),
            str(root / "android/app/src/main/java/org/hypseus/android/GameScanner.java"),
            str(root / "android/app/src/main/java/org/hypseus/android/GameCommands.java"),
            str(root / "android/app/src/main/java/org/hypseus/android/ControlMap.java"),
            str(root / "android/app/src/main/java/org/hypseus/android/VideoOptions.java"),
            str(root / "android/app/src/main/java/org/hypseus/android/ArcadeDisplay.java"),
            str(root / "android/tests/stubs/android/util/Base64.java"),
            str(root / "android/tests/ArcadeSetupTest.java"),
            str(root / "android/tests/LauncherLogicTest.java"),
        ], check=True, timeout=60)
        subprocess.run([
            java, "-cp", str(compiled), "org.hypseus.android.LauncherLogicTest", directory,
        ], check=True, timeout=30)
        subprocess.run([java,"-cp",str(compiled),"org.hypseus.android.ArcadeSetupTest",directory],check=True,timeout=30)


if __name__ == "__main__":
    main()
