# APK asset read benchmark

This separate test app compares reading support files directly from an APK
with reading identical files extracted into private storage. It helps measure
the cost of avoiding duplicate files; it does not measure game performance.

The benchmark copies all `assets/hypseus/` entries from a supplied APK, preserving each
entry's ZIP compression method and contents. A native JNI harness compares
`AAssetManager_open(AASSET_MODE_UNKNOWN)` / `AAsset_read` / `AAsset_seek64`
(the APIs used by the pinned SDL Android asset backend) with `fopen` / `fread` /
`fseek` on identical extracted private files.

The activity first extracts the files, then runs six workloads: all support
files, sound, graphics, fonts, and 256 deterministic non-monotonic 4 KiB reads
within each of the largest PNG and BMP. Sequential reads use 64 KiB chunks.
Timing includes open/read/seek/close, excludes allocation and checksum work.
Every output buffer is hashed outside the timed region and checked against the
other backend. Each workload has one warm-up pair and 30 measured pairs, with
alternating backend order. Input data fits in the page cache: these are **warm
cache** measurements, not cold-start, image/audio decoding, or gameplay tests.
APK seeks may benefit from Android buffering/decompressing a whole asset in RAM.

Build with JDK 17 and the repository's SDK/NDK versions:
Use your emulator's serial from `adb devices` in place of the example
`emulator-5556`.

```sh
python3 android/tests/asset-benchmark/build.py \
  --sdk /path/to/android-sdk --jdk /path/to/jdk17 \
  --apk android/artifacts/hypcade-arcade-armeabi-v7a-release.apk \
  --out local-tools/hypcade-assetbench-x86 --abi x86
adb -s emulator-5556 install local-tools/hypcade-assetbench-x86/benchmark.apk
adb -s emulator-5556 shell am start -n org.hypcade.assetbench/.Main
adb -s emulator-5556 logcat -d -s AssetBench:I '*:S'
# After PASS appears:
adb -s emulator-5556 exec-out run-as org.hypcade.assetbench cat files/results.csv \
  > local-tools/hypcade-assetbench-x86/results.csv
adb -s emulator-5556 uninstall org.hypcade.assetbench
```

Use `--abi armeabi-v7a` for a translated ARMv7 run on a compatible emulator.
Each output directory has its own temporary test signing key (not the app's
release key); uninstall this benchmark before installing another build signed
with a different key. It creates no game files and requests no permissions.
Benchmark output is local work data and is not included in the repository.
The command above saves your results under ignored `local-tools/`.
