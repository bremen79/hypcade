#!/usr/bin/env python3
"""Generate a small original MPEG-2/Vorbis/Singe integration fixture using FFmpeg."""
import argparse
from pathlib import Path
import shutil
import subprocess
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("destination", type=Path, help="New or existing test-data home directory")
args = parser.parse_args()
ffmpeg = shutil.which("ffmpeg")
if not ffmpeg:
    parser.error("FFmpeg with mpeg2video and libvorbis encoders is required")

game = args.destination.resolve() / "singe" / "media-test"
game.mkdir(parents=True, exist_ok=True)
subprocess.run([
    ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-f", "lavfi",
    "-i", "testsrc2=size=640x480:rate=30000/1001", "-t", "10", "-an",
    "-c:v", "mpeg2video", "-pix_fmt", "yuv420p", "-g", "15", "-bf", "0",
    "-b:v", "1800k", "-f", "mpeg2video", str(game / "media-test.m2v"),
], check=True)
subprocess.run([
    ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-f", "lavfi",
    "-i", "sine=frequency=440:sample_rate=44100:duration=10", "-ac", "2",
    "-af", "volume=0.15", "-c:a", "libvorbis", "-q:a", "3",
    str(game / "media-test.ogg"),
], check=True)
source = Path(__file__).with_name("media-test.singe")
shutil.copy2(source, game / source.name)
render_test = Path(__file__).with_name("render-test.singe")
shutil.copy2(render_test, game / render_test.name)
readonly_test = Path(__file__).with_name("readonly-test.singe")
shutil.copy2(readonly_test, game / readonly_test.name)
(game / "append.cfg").write_text("seed", encoding="utf-8")
(game / "media-test.txt").write_text(".\n0 media-test.m2v\n", encoding="utf-8")
with zipfile.ZipFile(game / "media-test.zip", "w", zipfile.ZIP_DEFLATED) as archive:
    archive.write(source, source.name)
print(f"Generated {game}")
print("Place the destination contents in the selected SD-card game folder, or import them.")
print("Game: singe")
print("Framefile: singe/media-test/media-test.txt")
print("Script: singe/media-test/media-test.singe (or media-test.zip to test ZIP loading)")
print("For a fixed-frame rendering comparison, select render-test.singe instead.")
