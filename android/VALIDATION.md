# Validation and known limits

This summarizes checks performed during development of Hypcade 0.1 on
November 8–9, 2026. It is a coverage record, not a guarantee that every supported
game, device or setting works. Earlier feature checks were not all repeated on
the final APK. No new runtime tests were performed while preparing these public
documents.

## Release build

All four signed version 0.1 release APKs assembled successfully: ARMv7 arcade,
ARM64 mobile, x86 arcade emulator and x86_64 mobile emulator. The final change
set the public version and its launcher/About labels; it was not installed or
runtime-tested. The preceding scoreboard build passed all four release lint
tasks, APK inspection and launcher regression checks. Lint passing means no
errors, not no warnings.

During development, packaging checks verified API 25 minimum, target SDK 36,
per-flavor ABIs, signatures, arcade/mobile touch and orientation separation,
`SDL_main` and 16 KiB ELF alignment for 64-bit libraries. ELF alignment is not a
test on an Android device using 16 KiB pages. Release artifact identities are in
[BUILD-PROVENANCE.json](BUILD-PROVENANCE.json); no byte-for-byte reproducibility
claim is made.

## Environments exercised

| Environment | Observed scope |
| --- | --- |
| Arcade1Up Yoga Flame, MT8168, Android 10/API 29, ARMv7 OS | Hardware MPEG-2 probes, repeated DL2 attract-mode seeks, native 1280×960 rendering, retained private settings and DL2 scoreboard display. |
| Android 7.1.1/API 25 x86 emulator | Installation, permissions, folder selection, controller setup, synthetic Singe playback, software decoding, background/resume and exit. Initial GPU CRT and plain-renderer fallback also exercised. This is API-level coverage, not a physical Android 7.1.2 cabinet test. |
| Android 9/API 28 x86 emulator | Direct removable-storage access, missing-card recovery, synthetic plain/ZIP Singe playback, input and lifecycle. ARMv7 APKs also ran through native translation. |
| Android 15/API 35 x86_64 emulator | Synthetic playback, mobile touch/Service controls, live window resizing, command import, index preparation, compressed assets, FPS and output-resolution CRT checks. Some earlier ROM/NEON checks used translated ARM64. |
| Host tools and QEMU | Launcher models, paths, clocks, indexes, guidance generation/retries and ARM decoder comparisons. |

An earlier API 26 emulator exercised the initial integration, but its old folder
import workflow is no longer part of Hypcade. Emulator audio output was disabled;
those runs do not establish audible quality or synchronization. Translation and
QEMU check execution/correctness, not native ARM throughput.

The project owner also reported that Hypcade worked on the Yoga Flame. That
report did not specify a complete game/setting matrix or a performance benchmark.
See [device capabilities](DEVICE-CAPABILITIES.md) for measured and advertised
hardware details, without private device identifiers.

## Functional coverage

| Area | Completed checks |
| --- | --- |
| Launcher and controller | Shared setup gating, required/optional assignments, duplicate rejection, persistence, setup reset, expanded-section scrolling and unavailable-option styling. Mobile requires either touch controls or a complete controller map. |
| Discovery and commands | Game inference, canonical containment, argument limits, first-discovery command import, quotes/comments, repeated banks, GUI precedence, malformed input and saved settings surviving rescans. |
| Storage | Direct game reads, read-only input data, missing storage handling, private settings and clean exit/relaunch. Fixture source hashes remained unchanged. |
| Video indexes | Host validation of malformed/truncated/out-of-range indexes and atomic publication failures; three-clip emulator run repaired a corrupt middle index before gameplay and reused valid indexes without rewriting them. Read-only fallback was host-tested. |
| Assets and sound loading | Font, PNG, BMP and WAV loads directly from APK; initial/cached playback slots and WAV music loading. Every packaged WAV decoded to its original bytes. Coin press-edge, repeat, mute and locking behavior was host-tested; touch Coin down/up reached the Lua fixture. |
| Lifecycle | Paired input events, background/resume, shutdown, return to launcher and fresh-process relaunch; production clock regressions include concurrent reads and shutdown timing. |
| Singe and mobile | Synthetic plain-script and ZIP games, mapped Service down/up, mobile Options button and hide/show behavior; resizing the live mobile window retained playback. No commercial Singe menu or physical Fold transition was validated. |
| UI options | Automatic persistence, score/FPS switches, command defaults and disabled unsupported controls. The final palette/focus changes and fast-startup splash change still need a focused physical-input/startup check. |

Index validation follows the native index format and is structural, not a
cryptographic media-content check: a different video of the same byte length
can still match an existing structurally valid index.

## Decoder and rendering checks

ARMv7 and ARM64 NEON implementations matched scalar output in 320,000 motion
compensation and 100,000 IDCT comparisons per ABI under QEMU. Progressive and
interlaced 720×480 streams (90 frames each, I/P/B pictures) also produced identical
full-plane hashes. These checks do not measure cabinet speed.

On the Yoga Flame, the production packet reader and MediaCodec decoder passed
172 sampled seek-frame checks across generated progressive/interlaced 720×480
streams, including open-GOP preroll. Sparse luma comparison against libmpeg2 had
worst mean difference below 0.009/255. A separate synthetic 90-frame probe took
635–787 ms per pass, with 192–216 ms decoder-thread CPU time. These are decode-only
figures, not end-to-end game benchmarks. Host recovery tests forced 96 failures
and matched all remaining software YUV frames and the input cursor.

The final output-pixel CRT pattern was checked on API 35 using 640×480 and
1440×1080 sources at the same 960×720 output. Sampled pattern pixels matched,
with two-row repetition, row contrast 25.5/255 and mask contrast 8.5/255. Resizing
the output to 1440×1080 retained the pattern. White overlays remained unchanged.
An earlier API 25 check verified plain output when the software renderer was
forced. It did not inject a shader-compiler failure. Final CRT performance on
Mali, arbitrary rotation/crops and every colorspace remain unmeasured.

Direct APK assets avoided 118 extracted resource files totaling 4,207,221 bytes;
only two writable input defaults totaling 5,447 bytes were created in the fresh
storage test. Filesystem allocation and Android caches vary by device. Lossless
WAV compression reduced the bundled sound payload by 444,183 bytes. A warm-cache
emulator asset benchmark measured about 3.2 ms to read all 4.21 MB from the APK,
versus roughly 0.9–1.2 ms from extracted files; this is not cold-start or cabinet
performance.

## ROM hints, scoreboards and two-player input

DLE21 and Space Ace hint generation completed eight DLE21 campaigns and three
Ace skill campaigns without lost lives. Production hint decoding recognized all
146 sampled post-death move states per game in offline retry tests, after
intentional deaths at three positions. Emulator play also showed DLE21 hints
after the first death. This does not cover every branch, DIP configuration or
later round.

DLE21/Ace lettering was compared with a real DL2 3.19 ROM prompt: the same bitmap
font, white glyph pixels, size and position were observed. DL2 prompt enable/disable
behavior was exercised in emulator sessions. DL2 has no additional app timing
cue; audible cue loudness in the other games was not established by silent runs.

The DL2 US 3.19 shared scoreboard was added using inspected ROM RAM fields. Its
option was enabled and the scoreboard appeared during SD attract playback on
the Yoga Flame. The observed presentation rate was about 18.2 fps, consistent
with that driver's nominal presentation interval; it is not the disc frame rate.
**Live score, life and credit changes, two-player turns and HD scoreboard display
have not been verified.** Testing stopped before those checks were completed.

The Start 2 mapping now includes the JNI range and native `SWITCH_START2` dispatch
that were initially missing. The fix built successfully, but successful two-player
starts on the cabinet have not yet been demonstrated. Do not describe this as a
passed gameplay test.

## Remaining coverage

- Sustained full-game speed, thermals, audible audio/video synchronization and
  real SD-card throughput, especially with HD media and CRT enabled together.
- Full physical-controller behavior, two-player turns, hotplug and simultaneous
  touch combinations across devices.
- Physical Android 7.1.2, Fold Z5 unfolding, Android 16/API 36 and 16 KiB-page runtime.
- Every ROM revision, commercial Singe script, difficulty and hint branch.
- Storage exhaustion, process death during writes and long-duration sessions.
- Renderer-device reconstruction: current behavior is a clean game exit, not
  automatic recovery within the same session.

## Repeating checks

The [build guide](README.md#build-the-app) describes the pinned toolchain.
Host checks and original-media generators live in `android/tests/`; offline
hint generation and retry tools live in `tools/offline-hints/`. Device tests
accept explicit device/toolchain arguments; inspect their help before running.
Use separately supplied game files where needed; no commercial ROMs or media
are distributed with the tests.

Raw logs, screenshots and temporary device state are local evidence, not source
repository contents. Preserve precise build/device details for new results and
update this summary only to the extent supported by those results.
