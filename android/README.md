# Hypcade setup and build guide

Hypcade adapts Hypseus Singe 3.0.2 for Android arcade cabinets. It runs on Android
7.1 (including 7.1.2) or newer and supports both Daphne ROM games and Singe
scripts. Phones are a secondary target.

The Android adaptation is maintained by **Francesco Orabona**.
Hypcade: Copyright (C) 2026 Francesco Orabona, GPL-3.0-or-later;
upstream components retain their original authorship and licences.

Start with the [project README](../README.md) for installation, the game-folder
layout, credits and licensing. This guide covers setup details and development.

- [Set up controls](#set-up-controls)
- [Find and launch games](#find-and-launch-games)
- [Video, sound and moves](#video-sound-and-moves)
- [Storage and permissions](#storage-and-permissions)
- [Game command files](#game-command-files)
- [Build the app](#build-the-app)
- [Development and troubleshooting](#development-and-troubleshooting)

## Set up controls

On an arcade, choose the game directory and complete **Configure controller**.
The game list appears after both steps are complete. The mapping applies to all
games; reopen **Directory & controller** to change it.

The wizard asks you to press and release each input. Return the joystick to
centre between directions. Up, Down, Left, Right, Action 1, Coin, Start and Exit
are required. Action 2, Action 3, Pause, Game options / Service and Start 2 players are optional:
use **Skip**, or hold an input for two seconds and release. Review the assignments
and save with Action 1 or Start. Android Back cancels without changing the
previous mapping. Duplicate assignments are rejected.

Directions move through the launcher; Action 1 or Start selects; Action 2 or
Exit goes back. Keyboard encoders, gamepad buttons and joystick axes are
supported. SDL gamepad mapping is always enabled. Android Back and volume
controls remain available.

For alternating two-player games, assign **Start 2 players** in controller
setup. This binding is optional and applies to all games. On mobile, press
**Start 2** beside **Start**. Both send the emulator's existing Player 2 Start
input; insert enough credits before starting. Players share the movement and
action controls and take turns where the game supports this mode.

On mobile, choose a directory and use the on-screen controls, which are enabled
by default. A physical controller is optional. If you disable touch controls,
you must configure a controller before starting a game.

## Find and launch games

Choose the parent folder containing `roms/`, your `.daphne` folders and any
`singe/` games. See the [example directory](../README.md#set-up-your-game-directory).
Press **Use this folder**, choose a game, then press **Start game**.

The scanner recognizes `.txt`, `.frame` and `.framefile` media maps. Folder and
file names identify the game; the framefile itself describes video locations,
not the ROM revision. For Singe, it pairs a matching `.singe` or `.zip` file,
or a single adjacent `.singe` script. The emulator checks ROM contents at launch.

Use **Rescan games** after adding files. Incomplete or ambiguous entries are
skipped. Use **Game Options** for manual framefile/script selection or a ROM
revision override. Completed selections and settings save automatically.
Scanning stops at 40,000 entries; select a smaller folder if that limit is reached.

A framefile starts with the media directory, relative to the framefile's folder.
Each following line gives a disc frame number and video filename:

```text
.
0 video.m2v
```

This is a format example, not a replacement for a game's supplied framefile.
Keep the correct frame offsets and filenames. Replace old desktop paths with
relative paths, match filename case, and keep all referenced files inside the
selected game folder. External Ogg audio uses the video's basename.

The arcade APK is ARMv7 and has no touch controls or rotation option. The mobile
APK is ARM64 and follows window changes, including folding and unfolding. A
64-bit CPU can run a 32-bit Android OS; check `adb shell getprop ro.product.cpu.abilist`
when choosing an APK. Both variants share the application ID
`org.hypseus.android` and replace one another when installed.

## Video, sound and moves

**Show moves** offers **Off**, **Max score** and **Fewest moves** for supported
ROM revisions. Max score selects the higher-scoring ROM route; Fewest moves
selects the route with fewer joystick/button actions. Watch Mode
uses the selected policy. With Show moves set to Off, Watch Mode uses Max score
while keeping the move display hidden. Dragon’s Lair II uses its native ROM
moves for either policy; Singe games keep their own script menus.

The DLE21 and Space Ace A3 move sets are derived from their ROM scene/step
tables and checked through complete games without a lost life. Randomized
starts, all three Space Ace skills and all four operator difficulties are tested.
All decoded rules and ranked alternatives are retained, including retry-only
steps; sampled winning games do not limit move coverage. Separate tests withhold
inputs to check that guidance resumes after a lost life.
Necessary zero-score actions, including Space Ace's final UP, are preserved.
These checks do not prove
that every retry context is covered or that the routes are globally optimal.


**Video & performance** has CRT scanlines, smoothing,
V-sync and Show FPS. **Game Options** has Fast startup and Show
score and lives for supported games. See the [settings table](../README.md#game-settings).
Changes take effect at the next launch. Unavailable controls are grayed out.

Fast startup applies the supported ROM shortcut and skips the emulator splash.
It does not skip video-index preparation. Dragon's Lair II has no ROM fast-boot
implementation.

DL2's driver presents at a nominal 18.2 fps, independently of the disc video's
frame rate. Its counter therefore shows `FPS: … (max 18.2)`; this is a driver
presentation limit, not a hardware performance rating. Other drivers without a
declared limit show measured FPS only.

Deinterlacing has no GUI switch. A game's `.commands` file can still pass
`-blend` to the native emulator. No configuration migration or cleanup is
performed.

Hardware MPEG-2 decoding is automatic and has no launcher toggle. Unsupported formats, devices,
field-coded streams and clips shorter than 12 frames use the software decoder.
A decoder failure also falls back to software; recovery can briefly pause the
video. ARM software decoding uses NEON where available. Neither path changes
emulated CPU timing or disc frame numbers.

CRT scanlines use a lightweight zfast-crt GPU shader. Video sampling, colour
conversion and the CRT pattern share one draw. Scanlines follow the final video
rectangle, with one dark row every two output pixels, independent of the source
resolution. Moves, subtitles and game overlays are drawn afterward. An
unsupported renderer or shader failure leaves the video unfiltered and writes
a log message. See the [shader credits](THIRD_PARTY_NOTICES.md#zfast-crt-shader).

**Show moves** and **Play move timing cue** support Dragon's Lair
Enhanced 2.1 (`dle21`) and Space Ace A3 (`ace`). White action text appears near
the bottom, up to about 400 ms before the move window. The font matches Dragon's
Lair II, with a transparent background and a small dark shadow.

Dragon's Lair II 3.19 (`lair2`, default version 6) uses its original ROM prompts.
Its extra timing-cue switch is disabled because the video already contains cues.
Singe games use their own Lua options menus: assign **Game options / Service**
or press **Options** on mobile. Unsupported ROM revisions have disabled move
controls. Showing moves displays guidance; **Watch Mode**, beside Start game,
plays automatically. It inserts coins until the game confirms a credit and
retries Player 1 Start until the game starts. During play, only Pause and Exit
remain available. Controller and touch gameplay inputs are blocked.

Offline generation decodes ROM alternatives and ranks routes for each objective.
Candidate inputs are checked against a simultaneous no-input simulation, and
complete policies retain every decoded rule and ranked alternative. Successful
death-free games and independent replays supply timing calibration, not the
coverage boundary. Required zero-score transitions are retained. Separate unassisted checks
exercise IRQ publication, Java polling, SDL delivery and button holds. Randomized
starts sample different paths; they do not establish every retry context or a
global optimum. See the [validation guide](VALIDATION.md).

DL2 Watch Mode reads the earliest acceptance phase in the US 3.19 ROM, including
special and exit move records. Its native on-screen prompts keep their original
presentation. The acceptance decoder does not change the emulated CPU or driver
timing.

Device media volume controls overall loudness. Command files can also set
`-volume_vldp` (video audio) and `-volume_nonvldp` (other game audio), from 0 to 64.
Difficulty and Space Ace skill already have GUI controls where supported.
Volume, seek delays, lives and coinage remain native or game-menu settings where
the game provides them.

## Storage and permissions

Game files are read in place. No ROM or video copy is made. Android 7.1–10 asks
for read-storage permission; Android 11 and later uses **All files access** to
allow native access to ROM archives and scripts. Cloud document-provider URIs
are not filesystem paths and cannot be selected with this browser.

The game directory only needs read access. Video indexes (`.dat`) are checked
for every clip before gameplay. Missing or invalid indexes are generated beside
writable videos; otherwise they go into internal storage. Valid indexes are
reused. The internal index cache is trimmed to 8 MiB before a launch, but a
running session can temporarily need more.

Settings, saves and logs live in private internal storage. Bundled fonts,
graphics and sounds load directly from the APK. Only two writable input defaults
(5,447 bytes) are extracted. Logs rotate at three files of 50 KB each. Singe's
standard file operations use private setting copies, with reads falling back
to the original game files. Updates to source settings seed a private copy only
for files up to 1 MiB. Unusual script filesystem operations or external commands
may not work.

Changing folders does not move or delete files. Profiles use relative paths,
so equivalent layouts can be used on different cards. If a card disappears,
reinsert it and use **Retry setup**, or choose another directory. Exit the game
before removing storage.

`/sdcard` usually means internal shared storage, not a removable card. Keep game
folders outside `Android/data/` and keep backups. Uninstalling or clearing app
data removes private settings and saves. Updates signed with the same release
key preserve them. This development project does not migrate old configuration
formats.

## Game command files

Place an optional `lair.commands` beside `lair.txt` (the same filename stem,
with `.commands` replacing the framefile extension). On first discovery,
Hypcade imports the file into the saved game settings. UTF-8, quoted arguments,
multiple lines, backslash line continuations and `#` comments outside quotes
are supported. This is an argument list, not an executable shell script:
do not include an executable, game ID, `vldp`, shell variables or shell commands.
Files are limited to 8192 bytes and 128 arguments.

For example:

```
-fastboot -scanlines -linear_scale
-bank 0 00100000
```

Supported GUI flags initialize their switches: fast startup, CRT scanlines,
smoothing, V-sync and FPS. Hardware decoding is automatic. With a command file,
missing boolean flags use the native defaults (fast startup is off); without
one Hypcade enables fast startup for supported games. Score remains enabled
by default; `-scorebezel` and `-useoverlaysb N` are represented by the GUI's
score/lives switch rather than retained as independent switches.

GUI changes take priority and are saved. All discovered games are saved,
including games you have not selected. Rescanning does not reread their command
files or overwrite settings. Editing a command file after discovery therefore
has no effect on that saved profile. Unrepresented game options, including
repeated `-bank` settings and `-version`, are retained for the native Hypseus
parser, which still validates supported options when the game starts.

Android supplies storage/script paths, screen geometry, and controller setup;
command-file overrides for these are discarded. Old CPU scanline spacing and
alpha settings are discarded because the Android CRT shader uses its own
pattern. Controller reorder is rejected with a configuration message.
Malformed command files and unsupported desktop hardware options produce a
scan error rather than silently starting with partial settings.


## Build the app

For a one-command build, run `./build-apks.sh release` from this directory.
It checks/prepares the pinned native dependencies and builds the two ARM release
APKs. Use `./build-apks.sh debug` for ARM debug APKs, or add `all` as the second
argument to include x86 and x86_64 emulator APKs. The script uses your configured
JDK and Android SDK (`ANDROID_HOME`, `ANDROID_SDK_ROOT`, or `local.properties`).
Set `HYPCADE_SIGNING_PROPERTIES` to sign release APKs with your private release
key during the build. Otherwise, build unsigned APKs and run `./sign-apks.sh`
afterward. The signer handles the ARM arcade and mobile APKs by default; use
`./sign-apks.sh all` to include the x86 emulator APKs. Configure
`HYPCADE_SIGNING_PROPERTIES` for your own private signing setup. Machine-specific
locations and maintainer settings are deliberately excluded from this guide.

Tested toolchain configuration:

| Component | Version |
| --- | --- |
| Java | JDK 17 |
| Android Gradle Plugin | 8.13.2 |
| Gradle wrapper | 8.13, distribution SHA-256 checked |
| Compile / target SDK | 36 / 36 |
| Minimum SDK | 25 |
| NDK | 28.2.13676358 (r28c) |
| CMake | 3.22.1 |
| SDL | 3.4.20, matching Java and native sources |
| SDL_image / SDL_ttf / SDL_mixer | 3.4.8 / 3.2.2 / 3.2.4 |
| libzip | 1.11.4 |

Install Android Studio or the Android command-line SDK, JDK 17, Git, and
Python 3.9 or newer. Set `ANDROID_HOME` to your SDK directory (or create the
usual `android/local.properties` with `sdk.dir=...`). Then, from this directory:

```bash
python3 bootstrap-deps.py
sdkmanager 'platforms;android-36' 'build-tools;35.0.0' \
  'ndk;28.2.13676358' 'cmake;3.22.1'
# Optional: configure HYPCADE_SIGNING_PROPERTIES in your private environment.
./gradlew :app:assembleRelease :app:lintArcadeRelease :app:lintMobileRelease
```

The results are `app/build/outputs/apk/mobile/release/app-mobile-release.apk` (ARM64)
and `app/build/outputs/apk/arcade/release/app-arcade-release.apk` (ARMv7). Install just the APK
matching the device OS ABI (a 64-bit CPU may run a 32-bit Android OS). You can also open
this `android` directory as a project in Android Studio after preparing the
dependencies. Release builds disable Java/native debugging and retain optimized
native code, R8 and resource shrinking. No private signing key is included in
source distributions.

`HYPCADE_SIGNING_PROPERTIES` names a private Java properties file containing
`storeFile`, `storePassword`, `keyAlias` and `keyPassword`. Supply your own
values; never commit this configuration or document private key locations in
the public repository.

Keep this file and the keystore private and backed up. Use the same release key
for future updates. Without this environment variable, Gradle produces unsigned
release APKs for external signing; it never falls back to a debug key. Local
`assembleDebug` builds remain available for development.

Official release APKs use a dedicated Hypcade release certificate. An APK
signed with another key cannot update them. Uninstalling clears private
settings and saves; game files outside app storage remain untouched. Arcade and mobile release APKs share the
same key and application ID and replace one another. See Android's
[app signing guide](https://developer.android.com/studio/publish/app-signing).
The certificate fingerprint is recorded in build provenance; the APK signature
contains the public certificate. Private signing material is never published.

A complete source archive contains the pinned dependency sources. For that
archive, the bootstrap script verifies their recorded hashes. In a Git
checkout without those sources, it downloads only the pinned commits and
required submodules. It refuses to reset or overwrite modified existing
checkouts. SDK/Gradle artifacts are still downloaded on the first build.
The source archive omits Git history and generated build outputs; it retains
the upstream source, Android changes, license files, and build scripts.
[BUILD-PROVENANCE.json](BUILD-PROVENANCE.json) records the selected toolchain,
upstream revision, and build-input checksums. Signing a rebuild with your own
key produces a different APK; byte-for-byte reproducibility is not claimed.

Select an ABI/flavor to build (default: both ARM variants):

```bash
./gradlew -Pabis=arm64-v8a :app:assembleDebug
./gradlew -Pabis=x86 :app:assembleDebug      # x86 Android emulator
./gradlew -Pabis=x86_64 :app:assembleDebug   # 64-bit Android emulator
```

The root `.github/workflows/android.yml` builds and lints a debug APK on
GitHub Actions when enabled in your own repository.


## Development and troubleshooting

Open **Debug → Display test** to check renderer and audio-device initialization
without game files. This does not test game speed or audible sound quality.
**Debug → View last log** shows the native log. **Exit** closes the launcher;
exiting a game ends its separate emulator process and returns to the launcher.

For a synthetic playback fixture, install FFmpeg with MPEG-2 and libvorbis
support and run from the `android` directory:

```bash
python3 tests/make-media-test.py /path/to/test-data
```

Select that directory on the device. The Singe framefile is
`singe/media-test/media-test.txt`; its script is `media-test.singe` in the same
folder. The fixture shows moving video, a frame counter and control input.
Its native log reports `ANDROID_MEDIA_TEST PASS` after frame 60. Choosing the
ZIP script instead also exercises ZIP loading.

Useful development checks, run from `android/`:

```bash
python3 bootstrap-deps.py --verify
python3 tests/test_android_clock.py
python3 tests/test_launcher_logic.py
./gradlew :app:lintDebug
```

See the [offline move tool](../tools/offline-moves/README.md) for generating ROM guidance
without video or real-time waits, and its
[Watch Mode verification guide](../tools/offline-moves/WATCH-VERIFY.md) for
host/Android checks and DL2 acceptance-window details. The
[validation guide](VALIDATION.md) summarizes the current results and limitations.

### How the Android build fits together

`app/jni/CMakeLists.txt` builds the engine as `libmain.so`, exporting `SDL_main`.
SDL remains shared; image, font, audio and MPEG-2 dependencies are linked into
the engine. Java and native SDL sources come from the same pinned checkout.
Each game runs in a separate process so a new launch starts with fresh state.
Android-specific changes stay behind platform guards where possible.

Release optimization, link-time optimization, R8 and resource shrinking reduce
the APK. JNI names are protected by `app/proguard-rules.pro`. Keep each flavor's
`app/build/outputs/mapping/<variant>/mapping.txt` to decode Java crash reports.
SDL supplies rendering, audio, input, timers and lifecycle support.

Unrotated video normally draws directly to the window. Rotation and unusual
crops use an intermediate texture. The decoder can prepare frames while the
renderer waits for refresh. The Android clock excludes time spent in the
background. Renderer-device loss currently exits the game cleanly; relaunching
creates a new graphics context.

The build supports common PNG/JPEG/bitmap artwork and WAV/Ogg/MP3/FLAC audio.
MIDI, APNG, AVIF, TIFF, WebP, Opus and tracker modules are not included. Desktop
scoreboard hardware, raw Linux multi-mouse/lightgun access and extra scoreboard
windows are unsupported. The app requests neither Internet nor raw Bluetooth
access; Android-paired controllers use the normal input path.

### Dragon's Lair II scoreboard

**Show score and lives** now uses the same graphical scoreboard as Dragon's
Lair I for the US 3.19 ROM (`lair2`, default revision or `-version 6`). It shows
both players' scores and lives plus the credit count, directly from the ROM's
state. Turning it off leaves the game's original video and text unchanged.
Other DL2 revisions remain disabled because their RAM layouts differ.
The shared artwork has one digit per life count and two credit digits; values
outside those display ranges are blank rather than truncated.

Implementation notes: US 3.19 (CRC32 `e9453a1b`) copies its data to segment
`0x1000`. Player life words are at offsets `0x56ac` and `0x56ae`, score words
at `0x56b0` and `0x56b2`, and credits at `0xa156`. The ROM's life-display routine
at `0x13b2`, score display at `0x166a` and credit display at `0x220a` establish
these fields. Scores are divided by ten, matching the ROM's own display and
high-score comparison. The adapter only reads RAM and updates the existing
image scoreboard at the driver's regular display tick. Commercial ROM images
and laserdisc media are not packaged; ROM-derived move metadata is included.

### Source and licensing

The upstream base is Hypseus Singe 3.0.2, commit
`a16e2521ee3233ef20c44e562008c47f4b4293df`. Android additions are GPL-3.0-or-later;
dependencies retain their own licenses. See [third-party notices](THIRD_PARTY_NOTICES.md),
[LICENSE](../LICENSE) and the [modification record](../MODIFICATIONS.md).
The main README explains credits, GPT-6 family and Codex assistance and distribution
of matching source. Complete source bundles accompany tagged APK releases, not every edit. Keep
generated artifacts, local settings and private signing material out of Git.
