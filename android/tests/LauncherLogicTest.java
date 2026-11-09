/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.List;

/** Regression checks for the production launcher model, without Android UI. */
public final class LauncherLogicTest {
    private interface CheckedAction { void run() throws Exception; }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private static void rejects(CheckedAction action, String message) throws Exception {
        try {
            action.run();
        } catch (IllegalArgumentException | IOException expected) {
            return;
        }
        throw new AssertionError(message);
    }

    private static void text(Path file, String value) throws IOException {
        Files.createDirectories(file.getParent());
        Files.write(file, value.getBytes(StandardCharsets.UTF_8));
    }

    private static String repeat(String value, int count) {
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < count; ++i) result.append(value);
        return result.toString();
    }

    private static LaunchConfig config(String game, String frames, String script,
                                       String extra) {
        return new LaunchConfig("profile-id", "Example", game, frames, script, extra);
    }

    private static String valueAfter(List<String> arguments, String option) {
        int index = arguments.indexOf(option);
        check(index >= 0 && index + 1 < arguments.size(), "Missing option " + option);
        return arguments.get(index + 1);
    }

    private static void tokenization() throws Exception {
        check(LaunchConfig.inferGame("dle21.daphne/dle21.txt").equals("dle21"), "DLE21 detection");
        check(LaunchConfig.inferGame("ACE.TXT").equals("ace"), "Case-insensitive ACE detection");
        check(LaunchConfig.inferGame("lair2.daphne/video.txt").equals("lair2"), "Folder detection");
        check(LaunchConfig.inferGame("singe/game/video.txt").equals("singe"), "Singe detection");
        check(LaunchConfig.inferGame("dle21.daphne/lair.txt").isEmpty(), "Ambiguous revision must ask");
        check(LaunchConfig.inferGame("unknown/video.txt").isEmpty(), "Unknown must ask");
        LaunchConfig defaults = config("dle21", "game.txt", "", "");
        check(!defaults.showMoves && !defaults.timingCue, "New profiles default assistance off");
        LaunchConfig assisted = new LaunchConfig("old", "Game", "dle21", "game.txt", "", "", true, true).withId("new");
        check(assisted.showMoves && assisted.timingCue, "Profile identity changes preserve assistance");
        check(LaunchConfig.splitArguments(null).isEmpty(), "Null extra options should be empty");
        check(LaunchConfig.splitArguments("  \t \n ").isEmpty(), "Whitespace should be empty");
        List<String> actual = LaunchConfig.splitArguments(
                "-bezel \"pics/art with spaces.png\" 'literal $HOME' escaped\\ value \"quote\\\"value\"");
        check(actual.equals(Arrays.asList("-bezel", "pics/art with spaces.png", "literal $HOME",
                "escaped value", "quote\"value")), "Quoted arguments or literal content changed: " + actual);
        check(LaunchConfig.splitArguments("'literal\\path'").equals(Arrays.asList("literal\\path")),
                "Single-quoted backslash should remain literal");
        rejects(() -> LaunchConfig.splitArguments("\"unterminated"), "Unclosed quote accepted");
        rejects(() -> LaunchConfig.splitArguments("dangling\\"), "Dangling escape accepted");
        rejects(() -> LaunchConfig.splitArguments("''"), "Empty quoted argument accepted");
        rejects(() -> LaunchConfig.splitArguments("unsafe\0suffix"), "NUL accepted");
        check(LaunchConfig.splitArguments(repeat("x ", 128)).size() == 128, "128-argument boundary changed");
        rejects(() -> LaunchConfig.splitArguments(repeat("x ", 129)), "Unbounded argument count");
        rejects(() -> LaunchConfig.splitArguments(repeat("x", 8193)), "Unbounded input length");
    }

    private static void settingsBounds() throws Exception {
        config("lair", "", "", repeat("a", 398)).validateSettings();
        rejects(() -> config("lair", "", "", repeat("a", 399)).validateSettings(),
                "Oversized native argument accepted");
        config("lair", "", "", repeat("é", 199)).validateSettings();
        rejects(() -> config("lair", "", "", repeat("é", 200)).validateSettings(),
                "Native bound must count UTF-8 bytes, not Java characters");
        rejects(() -> config("../lair", "", "", "").validateSettings(), "Invalid game ID accepted");
        for (String option : Arrays.asList("-homedir", "-DATADIR", "-romdir", "-ramdir", "-framefile", "-script", "-zlua", "-scorebezel", "-useoverlaysb")) {
            rejects(() -> config("lair", "", "", option + " alternative").validateSettings(),
                    "Managed option override accepted: " + option);
        }
        for (String option : Arrays.asList("-manymouse", "-scoreboard", "-usbscoreboard", "-scorepanel")) {
            rejects(() -> config("lair", "", "", option).validateSettings(),
                    "Unsupported platform option accepted: " + option);
        }
    }

    private static void pathsAndArguments(Path test) throws Exception {
        Path home = Files.createDirectories(test.resolve("home"));
        Path media = Files.createDirectories(home.resolve("vldp/demo"));
        text(media.resolve("intro.m2v"), "fixture");
        text(media.resolve("main.m2v"), "fixture");
        text(media.resolve("frames.txt"), "./\r\n-20 intro.m2v\r\n+10 main.m2v ignored trailing text");
        File root = home.toFile();
        LaunchConfig arcade = config("LAIR", "vldp/demo/frames.txt", "", "-fastboot -linear_scale");
        List<String> argv = Arrays.asList(arcade.arguments(root));
        check(argv.contains("-scorebezel"), "Score/lives default on for supported games");
        LaunchConfig noScore = new LaunchConfig("id", "test", "lair", "vldp/demo/frames.txt", "", "", false, false, false);
        check(!Arrays.asList(noScore.arguments(root)).contains("-scorebezel"), "Score/lives can be disabled");
        check(!noScore.withId("new").showScore, "Preserve disabled score preference");
        for (String unsupported : new String[]{ "ace91", "singe", "laireuro", "aceeuro", "cliff"})
            check(!LaunchConfig.supportsScore(unsupported), "No optional scoreboard for " + unsupported);
        check(Arrays.asList(config("lair2", "vldp/demo/frames.txt", "", "").arguments(root)).contains("-scorebezel"),
                "DL2 US 3.19 enables shared scoreboard");
        check(!LaunchConfig.supportsScore("lair2", Arrays.asList("-version", "5")), "Do not read 3.19 layout from 3.18");
        check(LaunchConfig.supportsScore("lair2", Arrays.asList("-version", "6")), "Explicit 3.19 scoreboard");
        check(!LaunchConfig.supportsFastBoot("lair2"), "Score support must not enable unsupported fastboot");
        check(!Arrays.asList(config("lair2", "vldp/demo/frames.txt", "", "-version 5").arguments(root)).contains("-scorebezel"),
                "Unsupported DL2 revisions do not receive scoreboard option");
        File privateState = Files.createDirectories(test.resolve("private-state")).toFile();
        List<String> separated = Arrays.asList(arcade.arguments(root, privateState));
        check(valueAfter(separated, "-homedir").equals(privateState.getCanonicalPath()), "State must be private");
        check(valueAfter(separated, "-datadir").equals(root.getCanonicalPath()), "Media must remain at source");
        check(valueAfter(separated, "-romdir").equals(new File(root, "roms").getCanonicalPath()), "ROM source changed");
        check(valueAfter(separated, "-ramdir").equals(new File(privateState, "ram").getCanonicalPath()), "RAM must be private");
        check(argv.get(0).equals("lair") && argv.get(1).equals("vldp"), "SDL argv[0] handling changed");
        check(valueAfter(argv, "-homedir").equals(root.getCanonicalPath()), "Wrong home directory");
        check(valueAfter(argv, "-datadir").equals(root.getCanonicalPath()), "Wrong data directory");
        check(valueAfter(argv, "-framefile").equals(media.resolve("frames.txt").toFile().getCanonicalPath()),
                "Relative framefile did not become a native path");
        check(argv.contains("-fullscreen") && argv.contains("-nomanymouse") && argv.contains("-gamepad"),
                "Required Android options missing");


        text(home.resolve("singe/game with spaces/start.singe"), "fixture");
        List<String> singe = Arrays.asList(config("singe", "vldp/demo/frames.txt",
                "singe/game with spaces/start.singe", "").arguments(root));
        check(valueAfter(singe, "-script").endsWith("game with spaces/start.singe"), "Script path was split");
        check(!singe.contains("-zlua"), "Plain script passed as ZIP");
        text(home.resolve("roms/package.ZIP"), "fixture");
        List<String> zip = Arrays.asList(config("singe", "vldp/demo/frames.txt", "roms/package.ZIP", "").arguments(root));
        check(zip.contains("-zlua") && !zip.contains("-script"), "ZIP mode missing");

        Path otherMedia = Files.createDirectories(home.resolve("vldp/video directory"));
        text(otherMedia.resolve("clip.m2v"), "fixture");
        text(media.resolve("relative.txt"), "..\\video directory\n0 clip.m2v\n");
        config("lair", "vldp/demo/relative.txt", "", "").arguments(root);

        check(LaunchConfig.relativePath(root, root).isEmpty(), "Root relative path");
        check(LaunchConfig.relativePath(root, home.resolve("vldp/demo/../video directory/clip.m2v").toFile())
                .equals("vldp/video directory/clip.m2v"), "Canonical relative path with spaces");
        check(LaunchConfig.relativePath(new File("/"), root).equals(root.getCanonicalPath().substring(1)),
                "Filesystem root containment");
        Path sibling = Files.createDirectories(test.resolve("home-other"));
        text(sibling.resolve("outside.m2v"), "fixture");
        rejects(() -> LaunchConfig.requireInside(root, sibling.resolve("outside.m2v").toFile()),
                "A shared path prefix escaped containment");
        rejects(() -> LaunchConfig.resolveFile(root, "../home-other/outside.m2v", "video"), "Traversal accepted");
        rejects(() -> LaunchConfig.resolveFile(root, media.resolve("main.m2v").toString(), "video"),
                "Absolute launcher path accepted");
        rejects(() -> LaunchConfig.resolveFile(root, "content://provider/document/1", "video"),
                "Content URI was passed as a filesystem path");
        rejects(() -> LaunchConfig.resolveFile(root, "C:\\games\\movie.m2v", "video"), "Windows path accepted");
        rejects(() -> LaunchConfig.resolveFile(root, "vldp/demo/missing.m2v", "video"), "Missing file accepted");

        // This check uses the real filesystem rather than a path-string mock.
        try {
            Files.createSymbolicLink(home.resolve("linked-video.m2v"), sibling.resolve("outside.m2v"));
            rejects(() -> LaunchConfig.resolveFile(root, "linked-video.m2v", "video"), "Symlink escaped containment");
            rejects(() -> LaunchConfig.relativePath(root, home.resolve("linked-video.m2v").toFile()),
                    "Relative path followed a link outside the selected folder");
        } catch (UnsupportedOperationException | java.nio.file.FileSystemException unsupported) {
            System.out.println("Symlink fixture unavailable on this host: " + unsupported.getClass().getSimpleName());
        }

        for (String contents : Arrays.asList("", "\n0 main.m2v\n", "\ufeff./\n0 main.m2v\n",
                "C:\\videos\n0 main.m2v\n", "./\n# standalone comment\n", "./\n0 absent.m2v\n",
                "./\n2147483648 main.m2v\n", "./\n")) {
            text(media.resolve("bad.txt"), contents);
            rejects(() -> config("lair", "vldp/demo/bad.txt", "", "").arguments(root),
                    "Invalid framefile accepted: " + contents.replace('\n', '|'));
        }
        text(media.resolve("bad.txt"), sibling.toString() + "\n0 outside.m2v\n");
        rejects(() -> config("lair", "vldp/demo/bad.txt", "", "").arguments(root),
                "Framefile redirected video outside the game root");
    }

    public static void main(String[] arguments) throws Exception {
        tokenization();
        settingsBounds();
        pathsAndArguments(Paths.get(arguments[0]));
        System.out.println("Launcher model regressions passed");
    }
}
