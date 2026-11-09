#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate native-resolution screenshots of the GPU CRT on a flat gray fixture.

Use --make-fixture DIR to create original test media. Run its discovered Singe
game at native 1280x960, capture plain and -scanlines output, then optionally
capture -scanlines -nohwaccel to check the plain-video fallback. Pass those PNGs
with --plain, --crt and --fallback. Requires FFmpeg, Pillow and NumPy.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--make-fixture', type=Path)
    parser.add_argument('--plain', type=Path)
    parser.add_argument('--crt', type=Path)
    parser.add_argument('--fallback', type=Path)
    parser.add_argument('--hd-crt', type=Path, help='Same output/scene with a 1440x1080 source')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    provenance = json.loads((root / 'android/shaders/SOURCE.json').read_text())
    original = root / 'android/shaders/zfast_crt.glsl'
    assert hashlib.sha256(original.read_bytes()).hexdigest() == provenance['sha256']
    if args.make_fixture:
        folder = args.make_fixture / 'singe/crt-test'
        folder.mkdir(parents=True, exist_ok=True)
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'color=c=gray:s=640x480:r=30000/1001',
                        '-t', '10', '-c:v', 'mpeg2video', '-q:v', '2',
                        '-pix_fmt', 'yuv420p', '-an', str(folder / 'crt-test.m2v')], check=True)
        (folder / 'crt-test.txt').write_text('./\n0 crt-test.m2v\n')
        script = (root / 'android/tests/render-test.singe').read_text()
        (folder / 'crt-test.singe').write_text(script.replace('RENDER COMPARISON', 'CRT OVERLAY CHECK'))
    if args.hd_crt and not args.plain:
        parser.error('--hd-crt requires --plain and --crt')
    if bool(args.plain) != bool(args.crt):
        parser.error('--plain and --crt are required together')
    if args.plain:
        import numpy as np
        from PIL import Image
        def pixels(path):
            return np.asarray(Image.open(path).convert('RGB'), dtype=np.float64)
        plain, crt = pixels(args.plain), pixels(args.crt)
        assert plain.shape == crt.shape
        height, width = plain.shape[:2]
        region = np.s_[height//3:height*4//5, width//5:width*4//5, :]
        baseline, filtered = plain[region], crt[region]
        assert baseline.std() < 1 and 120 < baseline.mean() < 135, 'Use the gray fixture'
        row_contrast = np.ptp(filtered.mean(axis=(1, 2)))
        mask_contrast = np.ptp(filtered.mean(axis=(0, 2)))
        assert row_contrast > 10, 'Scanlines must remain visible after scaling'
        assert mask_contrast > 2, 'The subtle GPU mask must be present'
        assert 0.75 < filtered.mean() / baseline.mean() < 1.1, 'Avoid excessive darkening'
        assert np.max(np.ptp(filtered, axis=2)) <= 1, 'Neutral YUV must remain neutral'
        white_overlay = np.all(plain > 245, axis=2)
        assert white_overlay.sum() > 100, 'Overlay fixture missing'
        assert np.max(np.abs(plain[white_overlay] - crt[white_overlay])) <= 1, 'Keep overlay text sharp'
        # A two-output-pixel cycle must remain stable across the entire image.
        rows = filtered.mean(axis=(1, 2))
        assert np.max(np.abs(rows[2:] - rows[:-2])) <= 1, 'Uneven output-row spacing'
        if args.hd_crt:
            hd = pixels(args.hd_crt)
            assert hd.shape == crt.shape
            assert np.max(np.abs(hd[region] - filtered)) <= 1, 'HD must retain the same CRT pattern as SD'
        if args.fallback:
            fallback = pixels(args.fallback)
            assert fallback.shape == plain.shape
            assert np.max(np.abs(fallback[region] - baseline)) <= 1, 'Unavailable shader must draw plain video'
        print(json.dumps(dict(row_contrast=float(row_contrast), mask_contrast=float(mask_contrast),
                              brightness_ratio=float(filtered.mean()/baseline.mean()),
                              sharp_overlay_pixels=int(white_overlay.sum()),
                              plain_fallback_checked=bool(args.fallback)), indent=2))
    print('CRT source provenance and requested checks passed')


if __name__ == '__main__':
    main()
