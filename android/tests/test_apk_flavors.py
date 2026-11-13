#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check shipped policy, not just Gradle declarations: touch code and orientation."""
import argparse
from pathlib import Path
import re
import subprocess
import zipfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--arcade', type=Path, required=True)
p.add_argument('--mobile', type=Path, required=True)
p.add_argument('--aapt', required=True)
p.add_argument('--arcade-mapping', type=Path, help='R8 mapping for an optimized release')
p.add_argument('--mobile-mapping', type=Path, help='R8 mapping for an optimized release')
a=p.parse_args()
for apk,arcade,abi in [(a.arcade,True,'armeabi-v7a'),(a.mobile,False,'arm64-v8a')]:
    with zipfile.ZipFile(apk) as z:
        dex=b''.join(z.read(n) for n in z.namelist() if re.fullmatch(r'classes\d*\.dex',n))
        for text in [b'Hide touch',b'Show touch',b'On-screen controls']:
            assert (text in dex) != arcade, (apk,text)
        mapping = a.arcade_mapping if arcade else a.mobile_mapping
        if mapping:
            match = re.search(r'^org[.]hypseus[.]android[.]TouchControls -> ([^:]+):$', mapping.read_text(), re.M)
            assert bool(match) != arcade, (apk, 'TouchControls R8 mapping')
            if match:
                descriptor = ('L' + match[1].replace('.', '/') + ';').encode()
                assert descriptor in dex, (apk, descriptor)
        else:
            assert (b'TouchControls' in dex) != arcade, (apk, 'TouchControls')
        for removed in [b'SDL gamepad mapping', b'Clear inherited advanced options', b'StorageChoice', b'Licenses & notices']:
            assert removed not in dex, (apk, removed)
        assert {n.split('/')[1] for n in z.namelist() if n.startswith('lib/')} == {abi}
    tree=subprocess.check_output([a.aapt,'dump','xmltree',str(apk),'AndroidManifest.xml'],text=True)
    activities={}
    for block in re.split(r' E: activity\b',tree)[1:]:
        name=re.search(r'android:name[^\n]*="([^"]+)"',block)
        orientation=re.search(r'android:screenOrientation[^\n]*\(type 0x10\)0x([0-9a-f]+)',block)
        if name:
            activities[name[1]]=int(orientation[1],16) if orientation else None
            if name[1] in ['org.hypseus.android.HypseusActivity', 'org.hypseus.android.LauncherActivity']:
                resize=re.search(r'android:resizeableActivity[^\n]*\(type 0x12\)0x([0-9a-f]+)',block)
                assert resize and bool(int(resize[1],16)) != arcade, (apk, name[1], 'resizable policy')
    assert activities['org.hypseus.android.HypseusActivity'] == (0 if arcade else 6), activities
    assert activities['org.hypseus.android.LauncherActivity'] == (0 if arcade else None), activities
    print(apk.name, 'arcade/mobile code separation and manifest orientation passed')
