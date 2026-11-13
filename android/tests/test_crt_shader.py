#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate native-resolution screenshots of the GPU CRT on a flat gray fixture.

Use --make-fixture DIR to create original test media. Run its discovered Singe
game at native 1280x960, capture plain and -scanlines output, then optionally
capture -scanlines -nohwaccel to check the plain-video fallback. Pass those PNGs
with --plain, --crt and --fallback. Requires FFmpeg, Pillow and NumPy.
The optional --native test requires existing shared SDL3/GLES2 libraries and
a C++11 compiler on Linux; it exercises production code with Mesa EGL.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import ctypes.util
import os
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--make-fixture', type=Path)
    parser.add_argument('--native', action='store_true', help='Exercise production GLES2 rendering with an installed Linux SDL3 library and Mesa EGL')
    parser.add_argument('--plain', type=Path)
    parser.add_argument('--crt', type=Path)
    parser.add_argument('--fallback', type=Path)
    parser.add_argument('--fps', action='store_true', help='Also check the unfiltered FPS: prefix when captured with -showfps')
    parser.add_argument('--hd-crt', type=Path, help='Same output/scene with a 1440x1080 source')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    provenance = json.loads((root / 'android/shaders/SOURCE.json').read_text())
    original = root / 'android/shaders/zfast_crt.glsl'
    assert hashlib.sha256(original.read_bytes()).hexdigest() == provenance['sha256']
    if args.native:
        library=ctypes.util.find_library('SDL3')
        if not library:parser.error('--native requires an existing shared SDL3 installation')
        scratch=root/'local-tools';scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='crt-frame-',dir=scratch) as folder:
            binary=Path(folder)/'frame-test'
            # Enable Android's collection completion hook without making the
            # Linux SDL/GLES library pretend it is an Android installation.
            (Path(folder)/'config.h').write_text('')
            collection=Path(folder)/'android-scoreboard.cpp'
            collection.write_text('#include <SDL3/SDL.h>\n#define __ANDROID__\n'
                '#pragma GCC diagnostic ignored "-Wunused-parameter"\n'
                '#include "'+str(root/'src/scoreboard/scoreboard_collection.cpp')+'"\n')
            subprocess.run([os.environ.get('CXX','c++'),'-std=c++11','-O2','-Wall','-Wextra','-Werror',
                '-I'+folder,
                '-I'+str(root/'android/third_party/SDL_ttf/include'),
                '-I'+str(root/'android/third_party/SDL/include'),'-I'+str(root/'src/3rdparty/plog/include'),
                '-I'+str(root/'android/app/jni'),'-I'+str(root/'src/video'),str(root/'android/tests/crt_frame_test.cpp'),
                str(root/'src/video/video_android.cpp'),str(collection),
                str(root/'src/scoreboard/scoreboard_interface.cpp'),
                str(root/'android/app/jni/android_crt.cpp'),'-l:'+library,'-lGLESv2','-o',str(binary)],check=True)
            subprocess.run([str(binary)],env={**os.environ,'EGL_PLATFORM':'surfaceless'},cwd=root,check=True)
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
    if args.fps and not args.plain:
        parser.error('--fps requires --plain and --crt')
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
        white_overlay[height//3:] = False
        assert white_overlay.sum() > 100, 'Overlay fixture missing'
        assert np.max(plain[white_overlay] - crt[white_overlay]) > 10, 'Overlay text must receive CRT scanlines'
        if args.fps:
            scale = 3 if height >= 1080 else 2 if height >= 600 else 1
            fps_region = np.s_[-8*scale:, 4*scale:32*scale, :]
            fps_plain, fps_crt = plain[fps_region], crt[fps_region]
            fps_white = np.all(fps_plain > 245, axis=2)
            assert fps_white.sum() > 20, 'FPS prefix missing'
            assert np.max(np.abs(fps_plain[fps_white] - fps_crt[fps_white])) <= 1, 'FPS text must stay unfiltered'
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
                              filtered_overlay_pixels=int(white_overlay.sum()),
                              plain_fallback_checked=bool(args.fallback), fps_checked=args.fps), indent=2))
    print('CRT source provenance and requested checks passed')


if __name__ == '__main__':
    main()
