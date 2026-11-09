#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check every bundled WAV is losslessly ZIP compressed, without duplicate originals."""
from pathlib import Path
import argparse,zipfile
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apk',action='append',required=True);a=p.parse_args()
root=Path(__file__).resolve().parents[2]
originals=sorted((root/'sound').rglob('*.wav'))
assert originals
for name in a.apk:
 with zipfile.ZipFile(name) as z:
  compressed=raw=0
  for f in originals:
   old='assets/hypseus/'+f.relative_to(root).as_posix();entry=old+'.bin';i=z.getinfo(entry)
   assert old not in z.namelist(),old
   assert i.compress_type==zipfile.ZIP_DEFLATED,entry
   assert z.read(entry)==f.read_bytes(),entry
   raw+=i.file_size;compressed+=i.compress_size
  actual={n for n in z.namelist() if n.startswith('assets/hypseus/sound/') and n.endswith('.wav.bin')}
  assert len(actual)==len(originals)
  print(f'{Path(name).name}: {len(originals)} identical WAVs; {raw} -> {compressed} bytes, saved {raw-compressed}')
