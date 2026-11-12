#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare an isolated debug player that can deliberately miss its first move.

Build from android/ with:
  ./gradlew -I ../local-tools/watch-death-fixture/init.gradle \
      -Pabis=x86,x86_64 :app:assembleArcadeEmulatorDebug

Before launching Watch Mode, create files/test-watch-muted with adb run-as in
org.hypseus.android.movetest. Remove it after observing the first lost life.
The player then resumes its ordinary inputs. The official source and release
build configuration are unchanged. All generated files stay in local-tools/.
"""
import hashlib
import json
from pathlib import Path


ROOT=Path(__file__).resolve().parents[2]


def replace_once(text,needle,replacement):
    if text.count(needle)!=1:
        raise RuntimeError('Watch player changed; review the test injection: '+needle.strip())
    return text.replace(needle,replacement,1)


def main():
    source=ROOT/'android/app/src/main/java/org/hypseus/android/WatchModeController.java'
    original=source.read_text();fixture=original
    fixture=replace_once(fixture,'    private boolean running;',
        '    private boolean running;\n'
        '    private java.io.File testMuteFile;\n'
        '    private boolean testMuted;')
    fixture=replace_once(fixture,'        if (running) return;\n        running = true;',
        '        if (running) return;\n'
        '        if (BuildConfig.DEBUG) {\n'
        '            testMuteFile = new java.io.File(org.libsdl.app.SDLActivity.getContext().getFilesDir(), "test-watch-muted");\n'
        '            testMuted = testMuteFile.isFile();\n'
        '        }\n'
        '        running = true;')
    fixture=replace_once(fixture,'            case PLAYING:\n                {\n',
        '            case PLAYING:\n                {\n'
        '                    if (testMuted) {\n'
        '                        if (testMuteFile.isFile()) break;\n'
        '                        testMuted = false;\n'
        '                        HypseusActivity.nativeRequestCurrentWatchMove();\n'
        '                    }\n')
    directory=ROOT/'local-tools/watch-death-fixture'
    java=directory/'java';java.mkdir(parents=True,exist_ok=True)
    (java/'WatchModeController.java').write_text(fixture)
    init="""allprojects { p ->
    p.plugins.withId('com.android.application') {
        p.extensions.getByName('androidComponents').finalizeDsl { extension ->
            extension.buildTypes.getByName('debug').applicationIdSuffix = '.movetest'
            extension.buildTypes.getByName('debug').versionNameSuffix = '-death-test'
            extension.sourceSets.getByName('main').java.exclude('**/WatchModeController.java')
            extension.sourceSets.maybeCreate('arcadeEmulatorDebug').java.srcDir(
                new File(p.rootProject.projectDir, '../local-tools/watch-death-fixture/java'))
        }
    }
}
"""
    (directory/'init.gradle').write_text(init)
    (directory/'provenance.json').write_text(json.dumps(dict(
        controller_source_sha256=hashlib.sha256(original.encode()).hexdigest(),
        fixture_sha256=hashlib.sha256(fixture.encode()).hexdigest(),
        test_application_id='org.hypseus.android.movetest',
        marker='files/test-watch-muted'),indent=2)+'\n')
    print('Prepared first-death test fixture:',directory)


if __name__=='__main__':main()
