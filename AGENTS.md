# Contributor guide: Hypcade

This guide applies to the whole repository.
Ask the user permission to change it when the architecture, build process or validation scope changes. Ask the user if to record user-facing behavior in the README. Never add a chronological handoff log here.

## Project scope

Hypcade 0.1 is an independent Android arcade adaptation of Hypseus Singe 3.0.2,
based on commit `a16e2521ee3233ef20c44e562008c47f4b4293df`. It changes the engine
and adds an Android launcher. Preserve upstream authorship and per-file notices.
The primary target is an Android arcade with physical controls; the phone build
is secondary. Keep SDL and the small launcher scope.

Minimum Android is 7.1 / API 25, including 7.1.2. Compile and target SDK are 36.
The application ID is `org.hypseus.android`. Public version `0.1` and internal
versionCode `40` are defined in `android/app/build.gradle`; main-screen and About
labels use `BuildConfig.VERSION_NAME`. Keep the upstream engine version separate.

There are no saved-configuration migrations. Do not add compatibility with old
development configurations unless the maintainer explicitly requests it.

## Read first

- `README.md`: installation, game directory layout, options, credits and AI disclosure.
- `android/README.md`: detailed setup, build, signing and development instructions.
- `MODIFICATIONS.md`: a thematic and synthetic summary of changes from upstream, not a changelog.
- `android/VALIDATION.md`: verified scenarios, evidence and remaining test limits.
- `android/THIRD_PARTY_NOTICES.md`, `NOTICE` and component licenses: attribution and packaging.
- `android/dependencies.lock.json` and `android/BUILD-PROVENANCE.json`: source pins and release identity.
- `doc/CmdLine.md`: native command-line behavior.

## Source map

| Area | Location |
| --- | --- |
| Launcher, discovery and profiles | `android/app/src/main/java/org/hypseus/android/`: `LauncherActivity`, `GameData`, `LaunchConfig`, `GameCommands`, `VideoOptions` |
| Global controller setup | `ControlMap`, `ControllerNavigation`, Android input bridges and `src/io/input.cpp` |
| Native activity and mobile controls | Main Java sources plus flavor-specific `src/mobile/` and `src/arcade/` |
| Cross-build and JNI | `android/app/jni/CMakeLists.txt`, `android_bridge.cpp` |
| Suspend-aware timing | `android/app/jni/android_clock.*`, `src/timer/timer.h` |
| Filesystem and APK assets | `src/io/sdl_path.h`, `src/io/android_storage.h`, Android storage helpers |
| Video and decoding | Shared `src/video/video.cpp`, Android backend `src/video/video_android.*`, `src/vldp/`, `src/ldp-out/`, JNI MPEG-2 and MediaCodec helpers |
| GPU CRT effect | `android/app/jni/android_crt*`, original source and provenance in `android/shaders/` |
| ROM guidance | JNI `arcade_guidance.*`, `arcade_signature.h`, `arcade_moves.inc`; generator in `tools/offline-moves/` |
| Game drivers and Singe | `src/game/` |
| Tests and original fixtures | `android/tests/`, `tools/offline-moves/` |

## Integration rules

- Keep SDL Java and native sources from the same pinned checkout. The engine is
  `libmain.so`, exports `SDL_main`, and receives argv[0] from SDL. Keep
  `packaging.jniLibs.useLegacyPackaging = true`: SDL loads the native library
  from its filesystem path. Preserve JNI names when changing R8 rules.
- Each game runs in the unexported `:emulator` process. End that process after a
  completed session so the next game starts with fresh desktop globals. Leave
  the launcher alive. Renderer-device loss currently exits the session cleanly;
  it does not rebuild all graphics state in place.
- The Android clock excludes background time while shutdown timeouts continue
  to advance. Do not replace it with unconditional wall time or SDL ticks.
- Decoder and renderer run on different threads. Preserve YUV locking and
  texture retirement/destruction on the rendering thread, including teardown.
  Never wait for a callback while holding a lock that callback needs.
- Preserve frame-accurate seeks, emulated CPU timing and software recovery.
  MediaCodec is optional; NEON/portable libmpeg2 remains the fallback. A faster
  synthetic decode probe is not evidence of full-speed gameplay.
- Keep Android video state and platform behavior in `src/video/video_android.*`,
  with small explicit hooks in shared `video.cpp`. Compile the backend only for
  Android; guard desktop-only code with conditional compilation.
- The single zfast-crt option filters video, native game text and recorded moves
  together on the output-pixel grid. Added score/lives, FPS, subtitles and bezels
  are drawn afterward without filtering. Unsupported renderers retain plain video.
  Native LDP1450 text and calculated moves use the same cached-font draw function.
- Arcade builds use fixed landscape, native-panel dimensions and no touch code.
  Mobile builds follow window size changes. Arcade play requires a complete
  global controller map; mobile play requires that map or enabled touch controls.
- Keep controller action IDs synchronized in `ControlMap`, JNI validation and
  native dispatch. Start 2 is action 12 and maps to `SWITCH_START2`. Release held
  inputs on pause, focus loss, cancellation, hiding controls and exit.

## Files, settings and arguments

- Read games directly from the selected filesystem directory. Do not copy game
  libraries into private storage or treat SAF/cloud URIs as native file paths.
  Android 7.1–10 uses read-storage permission; newer Android uses All files access.
  The manifest requests no Internet or raw Bluetooth permission.
- Shared setup and per-game preferences, saves and logs live in private internal
  storage. ROMs and media only require read access. Validate every clip's index
  before gameplay; publish new `.dat` files atomically beside writable videos,
  with a private fallback. Do not modify ROM/video payloads.
- SDL relative filenames on Android may refer to APK assets. Preserve explicit
  filesystem resolution and read-only APK fallback through the path adapters.
  Writes must remain filesystem writes. Lua working-directory changes must work.
- Support fonts, pictures and sounds load directly from the APK. Only the two
  writable input defaults (5,447 bytes) are extracted. WAV assets use lossless
  `.wav.bin` packaging; game-supplied filenames are unchanged. Edit source assets
  or the Gradle preparation task, never generated build output.
- Preserve canonical containment checks, case-sensitive framefile semantics,
  signed frame numbers, large-file handling and 64-bit sizes on ARMv7.
  Each native argument is limited to 398 UTF-8 bytes.
- Arguments are an argv list, never a shell command. A matching `.commands` file
  initializes a game only on first discovery. Saved GUI settings take priority;
  rescanning must not overwrite them. Retain unrepresented native options such
  as `-blend`, banks and ROM versions, subject to launch validation.
- Move controls are enabled only for supported ROM revisions. DL2 uses its own
  ROM prompts; Singe uses its native script menu through Service. Do not duplicate
  Lua menu behavior. DLE21 and Ace A3 use ROM-derived, separately ranked Max score
  and Fewest moves policies. Package every decoded ROM rule and every ranked alternative; sampled winning
  routes must never define runtime coverage. Validate causal acceptance against
  simultaneous no-input execution. Complete death-free plays and independent
  replays provide timing calibration and behavioral validation. Preserve necessary zero-score transitions, including
  Space Ace's final UP. Do not restore old acceptance-only tables.
- Cover Space Ace's three skills and four operator difficulties independently.
  Watch checks must include IRQ publication, Java polling and SDL queue delivery;
  an immediate-input replay alone does not validate Android timing. Test the merged
  lookup using only its bundled rows before publishing. Do not add learned or
  teacher-assisted fallbacks to the checker. Repeated randomized starts
  sample route changes; they do not prove every branch or global optimality.
  Reconstruct bundled rules from the complete ROM inventory and reject omitted
  windows or ranked alternatives, including unseen retry states. Account explicitly
  for death/ignored windows, equivalent diagonal controls and paths with no safe
  local completion. Withhold inputs to verify guidance resumes after a life loss
  across both strategies and all supported skills/operator difficulties.
- DL2 US 3.19 accepts moves from RAM segment `1000` offset `A160`; `A15C` is a
  later cue threshold and `A15A` closes the window exclusively. Input record types
  0, 1, 4 and 5 are valid. Preserve these ROM semantics rather than adding timing
  offsets or changing CPU/driver timing to make Watch Mode pass.
- The DL2 shared scoreboard currently supports US 3.19 only. Its stored score
  is ten times the displayed score. Other revisions must remain disabled until
  their layouts are established. See the Android guide for the RAM field mapping.

## Build and checks

Use JDK 17, Python 3.9+, Git, SDK 36, build-tools 35.0.0, NDK 28.2.13676358,
CMake 3.22.1 and the Gradle 8.13 wrapper (AGP 8.13.2). From `android/`,
`./build-apks.sh release` checks complete bundled ROM-rule coverage,
prepares/verifies dependencies and builds both ARM
release APKs. Use `./build-apks.sh release all` for all four device/emulator
flavors or `./build-apks.sh debug` for ARM debug APKs. Release signing requires
the private `HYPCADE_SIGNING_PROPERTIES` file. For direct Gradle development
builds, pass its path through that environment variable. To sign an unsigned
release build afterward, run `./sign-apks.sh` for ARM APKs or
`./sign-apks.sh all` for all four flavors. Set `HYPCADE_SIGNING_PROPERTIES`
using your own private signing configuration. Keep signing locations and other
machine-specific details out of tracked documentation.
For direct Gradle development builds:

```bash
python3 bootstrap-deps.py
./gradlew --no-daemon :app:assembleDebug :app:lintDebug
```

The default builds ARM64 mobile and ARMv7 arcade. Add
`-Pabis=arm64-v8a,armeabi-v7a,x86,x86_64` for all four flavors. Run Gradle builds
sequentially in a checkout. Outputs are under `app/build/outputs/apk/<flavor>/`.
The x86 flavors are `arcadeEmulator` and `mobileEmulator`.

Release builds use `:app:assembleRelease` and the private
`HYPCADE_SIGNING_PROPERTIES` file described in the Android guide. Without it,
release APKs are unsigned; there is no debug-key fallback. Never commit keys or
passwords. Keep the existing release key for official updates.

Run checks relevant to the change unless the maintainer asks otherwise. Common
host checks from the repository root are:

```bash
python3 android/bootstrap-deps.py --verify
python3 android/tests/test_android_clock.py
python3 android/tests/test_launcher_logic.py
python3 android/tests/test_bundled_moves.py
```

Other focused tests cover guidance, asset paths, coin input, WAV packaging,
video indexes, NEON, hardware decode and CRT output. Consult each tool's arguments
before running it. Java/resource changes normally need assembly and lint; native
changes need both ARM builds. Input, storage, lifecycle and decoding changes need
the affected runtime scenario. Documentation-only changes do not need an APK build.
Honor explicit requests not to test or install on a device.

For move generation and Watch Mode changes, follow `tools/offline-moves/README.md`
and `WATCH-VERIFY.md` in that directory. Run the skill/difficulty matrix and
unassisted packaged-selector checks on the host and Android emulator. DL2's
video-less harness uses the production Java player, JNI guidance, i86 CPU and
driver methods; include its omitted-input negative controls. Compare backend
results and keep source fingerprints consistent with the final tested tree.
Distinguish video-less Android checks from actual APK runs through the launcher.

## Local tools and data

Do not create manually managed hidden directories for project tools, emulator
profiles, scratch data or private settings. Keep local-only work under the
visible root `local-tools/` directory, which is ignored by Git. Required
repository/provider metadata (such as `.git` and `.github`), environment-managed
integration directories, and tool-generated build caches are not project
work-data locations; leave them where their tools expect them.

Machine-specific setup notes belong in `local-tools/LOCAL-SETUP.md`, which is
explicitly excluded from Git. Consult it when present before local builds;
never copy its toolchain paths or signing locations into tracked guides.

Before installing a tool locally, check whether a system-wide or shared
installation already provides it. If it does not, ask the maintainer whether
they want a system-wide/shared installation before installing a project-local
copy. Only install locally after that option has been considered; put the copy
under `local-tools/`, never under a dot-directory. Prefer the shared
`ANDROID_HOME` SDK and its side-by-side packages over project-local SDK or NDK
copies. Keep local signing keys out of Git.

Inspect new release APK signatures, SDK/ABI declarations and flavor policies;
update release hashes and build provenance. Preserve warnings and test limitations
in reports. Do not call translated ARM execution a physical-device test.

Generate original test media with `android/tests/make-media-test.py` and FFmpeg.
The Lua fixture's `ANDROID_MEDIA_TEST PASS` marker confirms frame advancement,
not commercial-game accuracy or audible synchronization. Inspect native logs as
well as logcat; the launcher exposes its last-log viewer under Debug. Runtime
checks must go through the launcher rather than exporting the emulator activity.

## Public repository and releases

Commit source, build scripts, wrapper JAR, original support assets, required move
inputs, tests, licenses and documentation. Keep downloaded `android/third_party/`
checkouts out of Git; the lock file and bootstrap script fetch exact revisions.
Never reset a modified dependency checkout. Preserve local adaptations as source
or patches before excluding any dependency tree.

Keep build outputs, local tooling, device captures, game files and signing
material out of Git. The required bundled libmpeg2 `.tgz` and Gradle wrapper JAR
are source/build inputs, not disposable output. `android/upstream-changes.json`
compares public source paths with the pinned upstream; refresh it when the
published source set changes.

For a tagged binary release, provide matching complete source (including pinned
dependencies and their required submodules), notices and checksums alongside the
APKs. Do not create a source archive for each edit. GitHub's automatic source ZIP
omits ignored dependencies. Source bundles omit caches, toolchain installations,
private settings and keys. Dependency bundles without Git metadata need verified
`.hypseus-source.json` markers for `bootstrap-deps.py`.

Generate companion notices with `android/package-notices.py` after fetching
sources. Notices remain outside the APK. Preserve original component licenses:
for example, plog is MPL-2.0, not MIT. Android additions are GPL-3.0-or-later.
Retain the GPT-6 family and Codex development disclosure and artwork provenance.
