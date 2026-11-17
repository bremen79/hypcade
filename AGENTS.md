# Contributor guide: Hypcade

This guide applies to the whole repository. It records contributor rules and
source ownership, not implementation status or validation procedures.

- Keep factual state information in its canonical document and link to it
  elsewhere. Avoid duplicated descriptions, results and instructions.
- Leave the root README.md unchanged unless the maintainer explicitly requests
  changes to that file. Ask before adding user-facing behavior there.
- Ask before changing this guide when architecture or build responsibilities
  change. Never add a chronological handoff log.
- Keep descriptions of hands-on cabinet experience out of Markdown documentation.

## Canonical references

| Subject | Document |
| --- | --- |
| Installation, game layout and public overview | `README.md` |
| Android setup, configuration, toolchains, building and signing | `android/README.md` |
| Current Android features and engine differences | `android/MODIFICATIONS.md` |
| Validation | `android/VALIDATION.md` |
| Version summaries | `CHANGELOG.md` |
| Dependency pins | `android/dependencies.lock.json` |
| Credits and component licensing | `NOTICE`, `android/THIRD_PARTY_NOTICES.md` and component licenses |
| Native command-line options | `doc/CmdLine.md` |
| ROM policy generation and proofs | `tools/offline-moves/README.md` |

Consult these references before changing their area. Preserve upstream
ownership, per-file notices, the independent-fork identity, and the GPT-6 family
and Codex development disclosure. Keep the upstream engine version separate
from the application version in `android/app/build.gradle`.

## Source ownership

| Area | Location |
| --- | --- |
| Launcher, discovery, configuration and controls | `android/app/src/main/java/org/hypseus/android/` |
| Flavor-specific controls | `android/app/src/mobile/`, `android/app/src/arcade/` |
| Android cross-build, JNI and clock | `android/app/jni/` |
| Shared input | `src/io/input.cpp` |
| Android video backend | `src/video/video_android.*` |
| Shared video, player and decoder | `src/video/video.cpp`, `src/ldp-out/`, `src/vldp/` |
| Game drivers and Singe | `src/game/` |
| APK assets and filesystem adapters | `src/io/sdl_path.h`, `src/io/android_storage.h` |
| ROM guidance and generated includes | `android/app/jni/arcade_guidance.*`, `arcade_*policy.h`, `arcade_*moves.inc` |
| ROM generators and reusable analysis | `tools/offline-moves/` |

## Integration constraints

- Keep SDL Java and native sources on the same pinned checkout. Preserve
  `SDL_main`, JNI names used by R8, and filesystem loading of `libmain.so`
  through `packaging.jniLibs.useLegacyPackaging`.
- End the emulator process after a session while leaving the launcher alive.
  Keep suspend-aware emulation time separate from shutdown wall time.
- Preserve frame-accurate seeks, emulated CPU timing and software decoder
  recovery. Keep Android platform behavior in its backend, with small guarded
  hooks in shared sources.
- Preserve YUV locking and render-thread texture ownership. Never wait for a
  callback while holding a lock that callback needs.
- Preserve game-layer CRT ordering and unfiltered overlays. Keep the shared
  cached-font path for native game text and calculated moves.
- Keep arcade controls and rendering separate from mobile touch/window handling.
  Synchronize action IDs across Java, JNI validation and native dispatch.
  Release held inputs on interruption, cancellation and exit.
- Read game libraries directly from their selected filesystem directory.
  Preserve canonical containment checks, case-sensitive framefiles, signed
  frame numbers, large-file handling and read-only APK-asset fallback.
  Do not modify ROM/video payloads or redirect writes into APK assets.
- Keep saved settings authoritative over discovery-time `.commands` defaults.
  Pass an argv list rather than a shell command. Do not add development-config
  migrations or compatibility layers without an explicit request.
- Change support assets at their source or preparation task, never in generated
  output. Preserve lossless WAV packaging and atomic video-index publication.
- Keep ROM guidance revision-guarded, cardinal/button only, and timed from the
  running ROM. Retain complete decoded inventories and ranked alternatives;
  sampled routes must not define coverage. Preserve required zero-score actions.
- Keep DL2's native prompts and Singe's script menus separate from calculated
  DL1/Space Ace guidance. Preserve ROM acceptance semantics and existing
  scoreboard revision guards.

## Workspace and build hygiene

- Any run should use little memory and little cpu, ask the user permission to run heavier computations.
- Put manually managed local tools, scratch output and private notes under the
  visible, ignored `local-tools/` directory. Leave provider metadata and
  tool-managed caches in their expected locations.
- Consult `local-tools/LOCAL-SETUP.md` when present. Never copy machine-specific
  paths, signing locations or secrets into tracked documentation.
- Prefer existing shared tool installations. Before installing a tool, check
  system/shared availability and discuss that option with the maintainer before
  installing a project-local copy.
- Run Gradle builds sequentially in a checkout. Follow the Android guide for
  toolchain and signing configuration; retain the official release identity
  and never introduce a debug-key fallback for release signing.
- Do not reset modified dependency checkouts. Preserve necessary adaptations
  as source or patches before changing pins or excluding downloaded trees.
- Keep build outputs, local tooling, game payloads, captures, private settings
  and signing material out of Git. Required source archives and wrapper JARs
  are build inputs, not disposable output.
- Refresh `android/upstream-changes.json` when the public source set changes.
  Generate companion notices from pinned sources and preserve their licenses.
- Tagged binaries require matching complete source, dependencies, notices and
  checksums. Follow `doc/RELEASING.md`; do not generate a source archive for
  each edit or rely on GitHub's automatic ZIP to include ignored dependencies.
