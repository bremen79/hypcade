<p align="center">
  <img src="android/artwork/hypcade-icon.png" alt="Hypcade arcade cabinet and laserdisc logo" width="240">
</p>

# Hypcade 0.1

**An Android arcade adaptation of [Hypseus Singe](https://github.com/DirtBagXon/hypseus-singe), the laserdisc game emulator**

Hypcade brings Hypseus Singe to Android Arcade1Up cabinets, with joystick-and-button
navigation, a small game launcher, and games read directly from an SD card or
another selected folder. Android 7.1 (API 25), including 7.1.2, or newer is required.

This project includes Android platform integration and modifications to the
emulator engine. This is an independent project, not an official Hypseus Singe
release. Hypseus Singe and its predecessors remain the foundation of the emulation; Hypcade does not claim to have created that engine.

## Arcade cabinets first

The primary build is for Arcade1Up Android arcades: physical controls, fixed landscape,
native-panel output (1280×960 on the Yoga Flame) with aspect-ratio preservation, and no on-screen control overlay.
The ARMv7 arcade APK targets the cabinet configuration used during development.
The ARM64 mobile build is a secondary convenience for phones and testing, with
touch controls and mobile orientation behavior retained.

- Scan a selected game folder and choose a game to run.
- Configure arcade directions and buttons by pressing each input.
- Read ROMs, videos and scripts in place; keep small saves, settings and logs
  in private storage. Store video indexes beside writable media, with an internal fallback.
- Use hardware MPEG-2 decoding with an ARM NEON software fallback and OpenGL ES
  rendering, with optional scanlines and other video settings.
- Enable score-verified move guidance for some Dragon’s Lair I and Space Ace ROMs,
  plus Dragon’s Lair II’s own ROM prompts.

No commercial game ROMs or laserdisc media are included. Supply your own game
files. The repository only includes emulator support assets and synthetic test data
with their existing notices.


**Show moves** offers **Off**, **Max score** and **Fewest moves** for supported
ROM revisions. Max score follows the recorded route with the higher score;
Fewest moves follows the route with fewer joystick/button actions. Watch Mode
uses the selected policy. With Show moves set to Off, Watch Mode uses Max score
while keeping the move display hidden. Dragon’s Lair II uses its native ROM
moves for either policy; Singe games keep their own script menus.

The DLE21 and Space Ace A3 move sets are derived from their ROM scene/step
tables and checked through complete games without a lost life. Randomized
starts and all three Space Ace skills are tested. These checks do not prove
that every retry context is covered or that the routes are globally optimal.

## Install and run

1. Install the Hypcade arcade APK.
2. Choose the existing folder containing your game files.
3. Use **Configure controller** and save the mapping. Directory and controller setup are required before the game list and options appear. The mapping applies to every game.
4. Choose a scanned game and press **Start game**. Use **Directory & controller** to change shared setup later; resetting the controller requires configuring it again.

A secondary mobile APK is available for ARM64 phones. On mobile, controller configuration is optional:
choose the game folder and play using the on-screen controls, enabled by default.
If you turn those controls off, configure a controller before starting a game. Both builds use the same Android application ID and signing identity and replace one another when installed; they are not
separate applications.

See the [Android setup and build guide](android/README.md) for folder layouts,
permissions, supported ROM revisions, options and troubleshooting.

## Set up your game directory

Create a folder such as **HypcadeGames** on the SD card. Keep it outside the
app’s `Android/data/` directory so uninstalling the app does not remove your
game files. Select **HypcadeGames** itself in the launcher, not an individual
video file or the `roms` subfolder.

A typical layout is:

```text
HypcadeGames/
├── roms/
│   ├── dle21.zip                 # Dragon’s Lair Enhanced 2.1 ROM set
│   ├── ace.zip                   # Space Ace A3 ROM set
│   └── lair2.zip                 # Dragon’s Lair II 3.19 ROM set
├── dle21/
│   ├── dle21.txt                 # framefile
│   ├── video.m2v                 # example MPEG filename
│   └── video.ogg                 # matching external audio, if used
├── ace/
│   ├── ace.txt
│   ├── video.m2v
│   └── video.ogg
├── lair2/
│   ├── lair2.txt
│   ├── video.m2v
│   └── video.ogg
└── singe/                        # optional Singe games
    └── mygame/
        ├── mygame.txt            # framefile
        ├── mygame.singe          # game script
        ├── video.m2v
        ├── video.ogg
        └── ...                  # the game’s other required assets
```

The `video.m2v`/`video.ogg` names are examples. Keep the media filenames, ROM ZIP
contents, scripts and additional assets supplied with your game. Games can use
several video/audio files. Do not substitute a different ROM revision while
keeping another set’s name. Hypcade includes neither the ROMs nor the videos.

**A framefile is a text file that tells the emulator where the video is and
which disc frame begins each video file.** Its first line gives the media
directory, relative to the framefile’s own folder; subsequent lines contain a
frame number and MPEG filename. For example, a single-file layout might use:

```text
.
0 video.m2v
```

Here `.` means “the same folder as this framefile.” 
Preserve your game’s actual frame numbers and file mappings. Replace PC-only directory paths
such as `C:\Games\...` with the correct relative directory. Android filenames
are case-sensitive, and every referenced media file must stay inside the game
folder selected in Hypcade. External Ogg audio uses the video’s matching basename.

For Singe, keep the script and its relative asset layout intact. Matching names
such as `mygame.txt` and `mygame.singe` allow the scanner to pair them. Other
supported layouts, including a `vldp/` hierarchy, are described in the
[Android guide](android/README.md).

After copying your files to the SD card:

1. Open **Hypcade → Choose game folder / SD card**.
2. Grant the requested storage access, open **HypcadeGames**, and choose
   **Use this folder**. The game files only need read access.
3. Configure your arcade controls, wait for the scan, then select and start a game.
   Use **Rescan games** after adding or changing files.

Recognizable framefile/folder names identify the game; the framefile itself
contains media mappings, not a definitive ROM identity. If detection is wrong,
use **Game Options → Game / ROM override**. If a game is missing, check that
its framefile points to existing MPEG files and that the matching ROM ZIP or
Singe script is present. Saves, settings and logs use small private app directories.
Video indexes (`.dat`) are validated for every clip before gameplay. Missing or
invalid indexes are generated beside writable videos, or internally if that fails.
The first preparation can take time; valid indexes are reused. Hypcade does not
import or duplicate the videos.

## Game settings

Settings save automatically and take effect the next time you start a game.
Unavailable options are grayed out.

| Setting | What it does |
| --- | --- |
| Hardware MPEG-2 decoding | Uses the device's decoder when available; falls back to software when needed. |
| CRT scanlines | Adds a lightweight zfast-crt GPU effect. |
| Smooth video scaling | Softens enlarged pixels. |
| V-sync | Matches presentation to display refresh. Turning it off may reduce waiting but make motion less smooth. |
| Show FPS | Shows rendered frames per second in the bottom-left corner. |
| Fast startup | Shortens startup in supported games. |
| Show score and lives | Enables the optional scoreboard in supported games. |

Move guidance is available for Dragon's Lair Enhanced 2.1 and Space Ace A3
when the selected move has ROM evidence of a score increase; Dragon's Lair II
3.19 uses its native prompts. Dragon's Lair I and Space Ace show white action text near
the bottom of the video and offer an optional timing cue. Dragon's Lair II uses
its own ROM prompts and the cues already in its video.

Singe games keep their own options menus. Assign **Game options / Service**
in controller setup to open a game's menu where supported. On mobile, use the
**Options** touch button.

Pressing Coin plays a short coin-slot sound to confirm the input. The game
itself decides whether to award a credit. The CC0 recording is by
[bassmosphere](https://freesound.org/people/bassmosphere/sounds/384700/);
see the [asset credits](android/THIRD_PARTY_NOTICES.md).

Optional `.commands` files initialize a game's settings when it is first
found. Saved GUI choices take priority and survive rescans. See the
[command-file guide](android/README.md#game-command-files).

## Storage and video

ROMs and videos stay in the selected folder. Settings, controller mappings,
saves and logs use private internal storage. Uninstalling or clearing app data removes these settings and saves.

The arcade build uses the panel's landscape resolution, which is 1280×960 on
the tested Yoga Flame.
The mobile build also follows window changes when a phone folds or
unfolds. Both preserve the game's aspect ratio.

The CRT effect runs in the existing GPU draw, after video sampling, with one
dark row every two display pixels. Moves and game overlays remain sharp.
Unsupported renderers show plain video.

## Status and testing

This was tested on an **Arcade1Up Yoga Flame** cabinet.

The tested scenarios and remaining gaps, including two-player starts and DL2
scoreboard counters, are recorded alongside automated checks and Android
7.1/9/15 emulator results in
[VALIDATION.md](android/VALIDATION.md). These include storage, playback, input,
launcher and selected move/retry scenarios.

## Upstream and attribution

The base is **Hypseus Singe 3.0.2**, pinned to commit
[`a16e2521ee3233ef20c44e562008c47f4b4293df`](https://github.com/DirtBagXon/hypseus-singe/tree/a16e2521ee3233ef20c44e562008c47f4b4293df).

- **Hypseus Singe — DirtBagXon and contributors.** Copyright (C) 2021–2026 DirtBagXon.
- **Hypseus — Jeffrey Clark and contributors.** Copyright (C) 2016 Jeffrey Clark.
- **Daphne — Matt Ownby and contributors.** Copyright (C) 1999–2013 Matt Ownby.
- **Singe — Scott Duensing**, with subsequent work by Hypseus Singe contributors.
- **Jeff Nyman’s laser-vault** supplies the attributed foundation for parts of
  the move-guidance and offline move-generation work.

These credits summarize the lineage; original per-file copyrights and license
notices remain authoritative. See [NOTICE](NOTICE), the preserved
[upstream README](doc/UPSTREAM-README.md), and
[third-party notices](android/THIRD_PARTY_NOTICES.md) for dependencies and assets.

Hypcade contributors have modified the upstream sources for Android arcade use. Changes include storage/path handling, lifecycle and timing, video rendering and ARM decoding, input, ROM move guidance,
Android packaging, and the launcher. [MODIFICATIONS.md](MODIFICATIONS.md) summarizes
the changes for the first public release. Original authors’
notices have not been replaced with Hypcade attribution.

[Hypdroid](https://github.com/rhakka303/Hypdroid) is another independent Android
adaptation. Hypcade is based directly on the pinned Hypseus Singe source, not on Hypdroid;
no Hypdroid code was imported for this work.

## AI-assisted development

Hypcade-specific development used **OpenAI GPT-6 and Codex** extensively
for implementation, refactoring, debugging, test creation and execution, build
work, and documentation. Project requirements and feedback, including the
cabinet testing, came from me.

## License and corresponding source

Hypcade is distributed under **GNU GPL version 3 or, at your option, any later
version**, with no warranty, including no implied warranty of merchantability
or fitness for a particular purpose. You may redistribute and modify it under
the GPL. Read the complete [LICENSE](LICENSE).

Original component licenses and copyright notices are preserved. Some files
retain GPL-2.0-or-later or permissive notices, and dependencies retain their own
licenses; the project-level GPL notice does not replace those notices.

This repository contains the modified engine, launcher, build scripts, support
assets and license texts.

The app exposes a short **About** dialog. Full GPL and component notices remain
in this repository.
