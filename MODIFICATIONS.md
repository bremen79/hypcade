# What Hypcade changes

Hypcade **0.1** is an Android arcade adaptation of
[Hypseus Singe 3.0.2](https://github.com/DirtBagXon/hypseus-singe), based on commit
`a16e2521ee3233ef20c44e562008c47f4b4293df`. It includes changes to the emulator
engine as well as a new Android launcher. It is an independent project, not an
official Hypseus Singe release.

**Modification notice — 2026-11-09:** Hypcade contributors modified the upstream
sources for Android arcade use. This document summarizes the changes for the
first public release. Original copyright and license notices remain in place.

## An interface for arcade cabinets

The launcher lets players choose a game and change its options using a joystick
and buttons. It discovers games from their framefiles and scripts, saves settings
automatically, and highlights the selected control. Opening a settings section
scrolls its contents into view. Unavailable options are disabled.

Directory selection and controller setup are shared by all games. The arcade
build requires a configured controller before allowing play. The setup wizard
asks the player to press each direction and button, with optional assignments
for a second-player start, pause and the game's service menu.

The ARMv7 arcade build uses the panel's landscape resolution and has no touch
controls or rotation setting. A secondary ARM64 mobile build provides on-screen
controls, including Start 2 and a Singe Options button. It also follows window
size changes on foldable phones. Mobile users can play with touch controls or a
configured controller; at least one must be available.

## Games stay on the SD card

ROMs, videos, audio and scripts are read directly from the selected folder.
Hypcade does not import or duplicate the game library. Small settings, saves
and logs live in private internal storage.

Video indexes are checked before gameplay. Missing or invalid indexes are
created beside writable videos, with internal storage as a fallback. Valid
indexes are reused so later scene changes do not have to stop for parsing.
Index files are written through temporary files to avoid replacing a valid
file with an incomplete one.

Bundled graphics, fonts and sounds load directly from the APK, avoiding roughly
4.21 MB of duplicate files in internal storage. WAV effects are compressed
without changing their audio data and are reused after loading.

On first discovery, a game's optional `.commands` file supplies its initial
settings and native emulator switches. GUI choices take priority. Rescanning
preserves saved settings, while Android retains control of storage paths,
controller configuration and display geometry. Singe scripts keep their original
asset layout and use private copies for supported writable settings.

## Video decoding and rendering

Hypcade can use Android's hardware MPEG-2 decoder when a suitable codec is
available. Unsupported streams and decoder failures fall back to software.
The software decoder includes ARM NEON acceleration for motion compensation
and parts of the inverse transform, while retaining a portable fallback.
Seeking, frame ordering and game timing remain under the emulator's control.

Video normally draws directly to the OpenGL ES window. Rotation and unusual
crops retain an intermediate rendering path. Decoder and renderer threads
coordinate access to video data, and textures are destroyed on the rendering
thread.

The CRT option uses an adaptation of Greg Hogan's **zfast-crt** shader. Video
sampling, colour conversion, scanlines and the subtle mask share one GPU draw.
The pattern follows the displayed image size, with one dark row every two output
pixels, so SD and HD videos use the same spacing. Text and game overlays are
drawn afterward. Unsupported renderers show plain video.

The launcher exposes hardware decoding, CRT, smoothing, V-sync and an optional
FPS counter. Deinterlacing remains available through the native `-blend` switch
in command files. The FPS counter measures presentation rate; for Dragon's Lair
II it also shows the driver's nominal 18.2 fps limit.

## Game assistance and scoreboards

Dragon's Lair Enhanced 2.1 and Space Ace A3 have optional move hints and timing
cues. Their hint tables are generated offline from user-supplied ROMs. Hints
appear near the bottom in white text on a transparent background, using the
same bitmap font as Dragon's Lair II. Recognition accounts for retries after
death. Coverage is specific to the supported ROM revisions and explored paths.

Dragon's Lair II US 3.19 uses its own ROM prompts, controlled by the launcher
setting. It has no extra timing-cue option because the video already supplies
cues. Singe games retain their original Lua options menus rather than receiving
a duplicate hint system from Hypcade.

The optional score-and-lives display reuses Hypseus's graphical scoreboard.
For Dragon's Lair II US 3.19, Hypcade adds a read-only connection to both players'
ROM score and life values and the credit count. Other DL2 revisions remain
unsupported. The stored score is divided by ten for display, matching the ROM.
This addition does not change scoring rules or game memory.

Fast startup uses the existing shortcut in supported game drivers and skips
the emulator splash. A short coin-slot sound confirms a coin-button press;
credit acceptance remains the game's responsibility. Player 2 Start uses the
emulator's existing input and supports alternating play where the game allows it.

## Android integration and smaller packages

The app supports Android 7.1, including 7.1.2, and newer. Each game runs in a
separate native process, which exits when the session ends while the launcher
stays open. Emulator time excludes time spent in the background, and held
controls are released on interruption or controller disconnection.

Android-specific file handling distinguishes game files from APK assets and
supports large media files on both 32-bit and 64-bit devices. Platform guards
keep Android changes separate from desktop behavior where practical. A lost
graphics device currently ends the game cleanly; relaunching recreates it.

The build retains SDL for rendering, sound, input and lifecycle integration.
It uses optimized native code, link-time optimization, Java code shrinking and
resource shrinking. Separate APKs contain only the ABI and interface appropriate
to their target. Unused MIDI synthesis and its SoundFont, CPU-test ROM assets,
optional media formats and unsupported desktop hardware backends are excluded.
Their source notices remain preserved where applicable.

## Tools, artwork and attribution

The Android build, packaging tools, automated checks and synthetic media fixtures
are additions to the upstream project. The offline hint generator runs game
logic faster than real time without decoding videos. It includes an attributed
GPL-3.0-or-later subset of **Jeff Nyman's laser-vault**, pinned to revision
`1f12c84dfabf3c8e5d028c8804b2f96678c798fa`; its notices and source provenance are
kept in [tools/offline-hints/vendor](tools/offline-hints/vendor/).

Hypcade has its own cabinet-and-laserdisc logo, Android icons and TV banner.
its prompt and provenance are in [android/artwork](android/artwork/).

Development used **GPT-6-Astra and Codex** extensively for implementation,
refactoring, debugging, builds, tests and documentation. I provided requirements,
feedback and cabinet testing. See the
[AI-assistance disclosure](README.md#ai-assisted-development).

Hypseus Singe, Hypseus, Daphne and Singe remain the foundation of the emulator.
The NEON decoder work preserves libmpeg2's notices; the CRT shader retains its
attribution to Greg Hogan. The CC0 coin sound is credited to bassmosphere.
Dependencies keep their own licenses.

See [NOTICE](NOTICE), [LICENSE](LICENSE) and
[third-party notices](android/THIRD_PARTY_NOTICES.md) for credits and licensing.
Full license texts remain in the repository and the external release notices,
rather than inside the APK. APK redistribution must include access to the
matching complete corresponding source, not merely unchanged upstream code.

For setup and building, read the [Android guide](android/README.md). The
[validation record](android/VALIDATION.md) distinguishes executed checks,
user-reported results and remaining gaps; the feature summary above is not a
claim of complete game or hardware validation.
