<p align="center">
  <img src="android/artwork/hypcade-icon.png" alt="Hypcade arcade cabinet and laserdisc logo" width="240">
</p>

# Hypcade v0.2.1 by Francesco Orabona

**An Android arcade adaptation of [Hypseus Singe](https://github.com/DirtBagXon/hypseus-singe), the laserdisc game emulator**

Hypcade brings Hypseus Singe to Android Arcade1Up cabinets, with joystick-and-button
navigation, a small game launcher, and games read directly from an SD card or
another selected folder. Android 7.1 (API 25), including 7.1.2, or newer is required.

## Arcade cabinets first

The primary build ("arcade") is for Arcade1Up Android arcades: physical controls, fixed landscape,
native-panel output (1280×960 on the Yoga Flame) with aspect-ratio preservation, and no on-screen control overlay.
The "mobile" build is a secondary convenience for phones and testing, with touch controls and mobile orientation behavior retained.

Features of Hypcade:
- Automatic scan of game folder.
- Configuration of arcade joystick and buttons.
- Small use of internal memory.
- Use arcade hardware MPEG-2 decoding with an ARM NEON software fallback and OpenGL ES
  rendering, with optional scanlines.
- Shows moves for Dragon’s Lair I/II and Space Ace.
- "Watch Mode", where the computer plays with the selected correct moves.

No commercial game ROMs or laserdisc media are included. Supply your own game
files. The repository includes emulator support assets, synthetic test fixtures
and ROM-derived move metadata, with their existing notices.

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


## Detailed Instructions



Settings save automatically and take effect the next time you start a game.

The following game options are available:

| Setting | What it does |
| --- | --- |
| CRT scanlines | Adds a lightweight zfast-crt GPU effect. |
| Smooth video scaling | Softens enlarged pixels. |
| V-sync | Matches presentation to display refresh. Turning it off may reduce waiting but make motion less smooth. |
| Show FPS | Shows rendered frames per second in the bottom-left corner. |
| Fast startup | Shortens startup in supported games. |
| Show score and lives | Enables the optional scoreboard in supported games. |


**Show moves** offers **Off**, **Max score** and **Fewest moves** for supported
ROM revisions. Max score selects the higher-scoring ROM route; Fewest moves
selects the route with fewer joystick/button actions. Watch Mode
uses the selected policy. With Show moves set to Off, Watch Mode uses Max score
while keeping the move display hidden. Dragon’s Lair II uses its native ROM
moves for either policy; Singe games keep their own script menus.

The DLE21, Space Ace A3 and Space Ace Enhancement 1.0 move sets are derived
from their ROM scene/step tables. The table below summarizes independently
replayed, death-free games. Ranges reflect randomized routes; counts refer to
accepted joystick/button actions, excluding coins and Start.

| Game / ROM | Skill | Fewest moves: actions | Score | Max score: actions | Score |
| --- | --- | ---: | ---: | ---: | ---: |
| Dragon’s Lair Enhanced 2.1 (`dle21`) | — | 147 | 314,457 | 155 | 333,333 |
| Space Ace A3 (`ace`) | Cadet | 85 | 185,686 | 134 | 257,784 |
| Space Ace A3 (`ace`) | Captain | 109–110 | 213,098 | 166 | 289,102 |
| Space Ace A3 (`ace`) | Ace | 142 | 216,092 | 212 | 371,338 |
| Space Ace Enhancement 1.0 (`sae`) | Cadet | 85–87 | 150,396–151,568 | 151 | 318,464–319,498 |
| Space Ace Enhancement 1.0 (`sae`) | Captain | 110 | 179,410 | 183 | 366,836 |
| Space Ace Enhancement 1.0 (`sae`) | Ace | 119 | 188,112 | 212 | 398,412 |
| Dragon’s Lair Rev. A (`lair_a`) | — | 191–202 | 305,041–360,613 | 192–205 | 305,536–350,198 |
| Dragon’s Lair Rev. B (`lair_b`) | — | 191–202 | 300,285–352,449 | 192–205 | 300,780–349,161 |
| Dragon’s Lair Rev. C (`lair_c`) | — | 191–202 | 300,285–352,449 | 192–205 | 300,780–349,161 |
| Dragon’s Lair Rev. D (`lair_d`) | — | 192–207 | 303,514–352,894 | 193–207 | 304,009–354,608 |
| Dragon’s Lair Rev. E (`lair_e`) | — | 192–198 | 325,753–326,124 | 193–199 | 326,248–326,619 |
| Dragon’s Lair Rev. F (`lair_f`) | — | 196–198 | 325,745–326,124 | 197–199 | 326,240–326,619 |
| Dragon’s Lair European (`laireuro`) | — | 207 | 202,599 | 207 | 202,599 |
| Dragon’s Lair Italian (`lair_ita`) | — | 69–76 | 73,949–88,250 | 69–76 | 73,949–88,250 |

The European and Italian rows cover all four native levels and two start times
on the host; their Android runtime checks are pending. Other rows cover the supported operator difficulty settings. Strategies rank
routes through the decoded tables; the ROM still chooses scene order, so this
is not a proof of a global optimum. Watch Mode may issue additional presses
because it delivers inputs through the normal polling and queue.
Dragon’s Lair II US 3.19 uses its native ROM prompts, with one move policy;
it has no separately calculated Max score/Fewest moves totals in this table.

Press **Watch Mode** beside **Start game** to play automatically. It waits for
the game to accept credits and Player 1 Start, then follows the selected moves.
Only Pause and Exit remain active during automatic play.

Singe games keep their own options menus. Assign **Game options / Service**
in controller setup to open a game's menu where supported. On mobile, use the
**Options** touch button.

Pressing Coin plays a short coin-slot sound to confirm the input. The game
itself decides whether to award a credit.

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

[VALIDATION.md](android/VALIDATION.md) explains the test setup, evidence, media
used and remaining gaps. These emulator results are separate from the earlier
cabinet test; the current changes have not been retested on physical ARM hardware.

## Upstream and attribution

Hypcade is developed and maintained by **Francesco Orabona**.
**Hypcade — Copyright (C) 2026 Francesco Orabona.**
Licensed under GPL-3.0-or-later. Upstream components retain their own notices.

Hypcade is an independent project, not an official Hypseus Singe release. Hypseus Singe and its predecessors remain the foundation of the emulation; Hypcade does not claim to have created that engine.

The base is **Hypseus Singe 3.0.2**, pinned to commit
[`a16e2521ee3233ef20c44e562008c47f4b4293df`](https://github.com/DirtBagXon/hypseus-singe/tree/a16e2521ee3233ef20c44e562008c47f4b4293df).

- **Hypseus Singe — DirtBagXon and contributors.** Copyright (C) 2021–2026 DirtBagXon.
- **Hypseus — Jeffrey Clark and contributors.** Copyright (C) 2016 Jeffrey Clark.
- **Daphne — Matt Ownby and contributors.** Copyright (C) 1999–2013 Matt Ownby.
- **Singe — Scott Duensing**, with subsequent work by Hypseus Singe contributors.
- **Jeff Nyman’s laser-vault** supplies the attributed foundation for parts of
  the move-guidance and offline move-generation work.

These credits summarize the lineage; original per-file copyrights and license
notices remain authoritative. See [NOTICE](NOTICE), the
[upstream README at the pinned revision](https://github.com/DirtBagXon/hypseus-singe/blob/a16e2521ee3233ef20c44e562008c47f4b4293df/README.md), and
[third-party notices](android/THIRD_PARTY_NOTICES.md) for dependencies and assets.
The [verbatim README snapshot](doc/UPSTREAM-README.md) preserves the original
text; its relative links refer to the upstream repository layout.

Hypcade contributors have modified the upstream sources for Android arcade use. Changes include storage/path handling, lifecycle and timing, video rendering and ARM decoding, input, ROM move guidance,
Android packaging, and the launcher. The [Android modification record](android/MODIFICATIONS.md) describes the current
differences from upstream, and the [changelog](CHANGELOG.md) summarizes each
version. Original authors’
notices have not been replaced with Hypcade attribution.

[Hypdroid](https://github.com/rhakka303/Hypdroid) is another independent Android
adaptation. Hypcade is based directly on the pinned Hypseus Singe source, not on Hypdroid;
no Hypdroid code was imported for this work.

## AI-assisted development

Hypcade-specific development used **OpenAI GPT-6 family and Codex** extensively
for implementation, refactoring, debugging, test creation and execution, build
work, and documentation. Project requirements and feedback, including the
cabinet testing, came from Francesco Orabona.

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
