#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Produce the external notices file to distribute alongside every APK."""
from pathlib import Path
import os
root=Path(__file__).resolve().parent.parent
files=[root/n for n in ('LICENSE','NOTICE','CHANGELOG.md','android/MODIFICATIONS.md','android/THIRD_PARTY_NOTICES.md')]
files+=sorted(p for p in (root/'android/licenses').rglob('*') if p.is_file())
for directory,dirs,names in os.walk(root/'android/third_party'):
 dirs[:]=sorted(d for d in dirs if d!='.git')
 for n in sorted(names):
  if n in ('LICENSE','COPYING','FTL.TXT') or n.startswith(('LICENSE.','COPYING.')):
   files.append(Path(directory)/n)
out=root/'android/artifacts/hypcade-licenses.txt'
out.parent.mkdir(parents=True,exist_ok=True)
with out.open('wb') as stream:
 stream.write(b'Hypcade release licenses, attribution and modification notices\nDistribute this file alongside the APKs. Original files remain in the source repository.\n')
 for p in files:
  stream.write(('\n\n===== '+p.relative_to(root).as_posix()+' =====\n\n').encode())
  stream.write(p.read_bytes())
print(f'{out.name}: {len(files)} source notice files, {out.stat().st_size} bytes')
