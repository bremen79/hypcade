#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the production Watch Mode player against a deterministic Android clock."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jdk',type=Path)
    args=parser.parse_args();root=Path(__file__).resolve().parents[2]
    jdk=args.jdk or (Path(os.environ['JAVA_HOME']) if os.environ.get('JAVA_HOME') else None)
    java=str(jdk/'bin/java') if jdk else 'java';javac=str(jdk/'bin/javac') if jdk else 'javac'
    sources=sorted((root/'android/tests/watch-stubs').rglob('*.java'))
    sources += [root/'android/tests/WatchModeControllerTest.java',
                root/'android/app/src/main/java/org/hypseus/android/WatchModeController.java']
    with tempfile.TemporaryDirectory(prefix='hypcade-watch-') as directory:
        subprocess.run([javac,'-encoding','UTF-8','-Xlint:all','-Werror','-d',directory,*map(str,sources)],check=True)
        subprocess.run([java,'-cp',directory,'org.hypseus.android.WatchModeControllerTest'],check=True)

if __name__=='__main__':main()
