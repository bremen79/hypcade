/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** The launcher model and argument validation; deliberately independent of Android UI classes. */
public final class LaunchConfig {
    static final String[] GAME_IDS = {"lair", "ace", "singe", "lair2", "lair_f", "lair_e",
            "lair_d", "lair_c", "lair_b", "lair_a", "laireuro", "lair_ita", "dle11", "dle21",
            "ace_a", "ace_a2", "ace91", "aceeuro", "sae", "astron", "astronp", "badlands",
            "badlandp", "bega", "begar1", "blazer", "cliff", "cliffalt", "cliffalt2", "cobra",
            "cobraab", "cobraconv", "cobram3", "esh", "eshalt", "eshalt2", "galaxy", "galaxyp",
            "gpworld", "gtg", "interstellar", "mach3", "roadblaster", "sdq", "sdqshort", "tq", "uvt"};

    /** Framefiles describe media, not ROM identity; only infer unambiguous names. */
    static String inferGame(String path) {
        if (path == null || path.isEmpty()) return "";
        File file = new File(path.toLowerCase(Locale.ROOT));
        String name = file.getName().replaceFirst("[.][^.]+$", "");
        String match = Arrays.asList(GAME_IDS).contains(name) ? name : "";
        for (File parent = file.getParentFile(); parent != null; parent = parent.getParentFile()) {
            String folder = parent.getName();
            String candidate = folder.endsWith(".daphne") ? folder.substring(0, folder.length()-7)
                    : folder.equals("singe") ? "singe" : "";
            if (Arrays.asList(GAME_IDS).contains(candidate)) {
                if (!match.isEmpty() && !match.equals(candidate)) return "";
                match = candidate;
            }
        }
        return match;
    }

    public final String id;
    public final String name;
    public final String game;
    public final String framefile;
    public final String script;
    public final String extraArguments;
    public final int moveMode;
    public final boolean timingCue;
    static final int SCORE_OFF = 0, SCORE_LEFT = 1, SCORE_RIGHT = 2, SCORE_TOP = 3;
    static final String[] SCORE_LAYOUTS = {"Off", "Left", "Right", "Top"};
    private static final String[] ACE_SCORE_LAYOUTS = {"Off", "Left", "Right"};
    public final int scoreLayout;
    public final int difficulty;
    public final int skill;

    private static final Set<String> MANAGED_OPTIONS = new HashSet<>(Arrays.asList(
            "-homedir", "-datadir", "-romdir", "-ramdir", "-framefile", "-script", "-zlua", "-scorebezel", "-scorebezel_layout", "-useoverlaysb"));
    private static final Set<String> UNSUPPORTED_OPTIONS = new HashSet<>(Arrays.asList(
            "-manymouse", "-scoreboard", "-scoreport", "-usbscoreboard", "-scorepanel"));

    public LaunchConfig(String id, String name, String game, String framefile, String script,
                        String extraArguments) {
        this(id, name, game, framefile, script, extraArguments, MoveMode.OFF, false);
    }

    public LaunchConfig(String id, String name, String game, String framefile, String script,
                        String extraArguments,
                        int moveMode, boolean timingCue) {
        this(id, name, game, framefile, script, extraArguments, moveMode, timingCue, SCORE_LEFT);
    }

    public LaunchConfig(String id, String name, String game, String framefile, String script,
                        String extraArguments, int moveMode, boolean timingCue, int scoreLayout) {
        this(id, name, game, framefile, script, extraArguments, moveMode, timingCue, scoreLayout,
                GameDifficulty.importedSelection(clean(game).toLowerCase(Locale.ROOT), splitArguments(clean(extraArguments))));
    }

    public LaunchConfig(String id, String name, String game, String framefile, String script,
                        String extraArguments, int moveMode, boolean timingCue, int scoreLayout, int difficulty) {
        this(id, name, game, framefile, script, extraArguments, moveMode, timingCue, scoreLayout, difficulty, 0);
    }

    public LaunchConfig(String id, String name, String game, String framefile, String script,
                        String extraArguments, int moveMode, boolean timingCue, int scoreLayout, int difficulty, int skill) {
        this.id = clean(id);
        this.name = clean(name);
        this.game = clean(game).toLowerCase(Locale.ROOT);
        this.scoreLayout = scoreLayout >= SCORE_OFF && scoreLayout < scoreLayouts(this.game).length
                ? scoreLayout : SCORE_LEFT;
        this.moveMode = MoveMode.selected(this.game, moveMode);
        this.difficulty = GameDifficulty.selected(this.game, difficulty);
        this.skill = GameDifficulty.selectedSkill(skill);
        this.timingCue = timingCue;
        this.framefile = clean(framefile);
        this.script = clean(script);
        this.extraArguments = clean(extraArguments);
    }

    private static String clean(String text) {
        return text == null ? "" : text.trim();
    }

    public LaunchConfig withId(String newId) {
        return new LaunchConfig(newId, name, game, framefile, script,
                extraArguments, moveMode, timingCue, scoreLayout, difficulty, skill);
    }

    static boolean supportsScorePlacement(String game) {
        return GameDifficulty.spaceAce(game) || game.equals("lair2") || game.equals("dle11") || game.equals("dle21") ||
                game.equals("lair") || game.matches("lair_[a-f]");
    }

    static String[] scoreLayouts(String game) {
        return GameDifficulty.spaceAce(game) ? ACE_SCORE_LAYOUTS : SCORE_LAYOUTS;
    }

    static boolean supportsScore(String game) {
        return Arrays.asList("lair", "lair_f", "lair_e", "lair_d", "lair_c", "lair_b", "lair_a",
                "dle11", "dle21", "ace", "ace_a", "ace_a2", "sae", "tq", "lair2").contains(game);
    }

    static boolean supportsScore(String game, List<String> options) {
        if (!game.equals("lair2")) return supportsScore(game);
        for (int i = 0; i < options.size(); i++) {
            if (options.get(i).equalsIgnoreCase("-version")) {
                if (++i >= options.size() || !options.get(i).equals("6")) return false;
            }
        }
        return true;
    }

    static boolean supportsFastBoot(String game) {
        return (supportsScore(game) && !game.equals("tq") && !game.equals("lair2")) ||
                Arrays.asList("cliff", "cliffalt", "cliffalt2", "gtg").contains(game);
    }

    public void validateSettings() {
        if (!game.matches("[a-z][a-z0-9_]{0,62}")) {
            throw new IllegalArgumentException("Enter a game ID such as lair, ace or singe.");
        }
        if (name.length() > 100) {
            throw new IllegalArgumentException("Keep the profile name under 101 characters.");
        }
        for (String argument : splitArguments(extraArguments)) {
            String option = argument.toLowerCase(Locale.ROOT);
            if (MANAGED_OPTIONS.contains(option)) {
                throw new IllegalArgumentException(option
                        + " is set by the launcher. Use the file fields above.");
            }
            if (UNSUPPORTED_OPTIONS.contains(option)) {
                throw new IllegalArgumentException(option
                        + " requires desktop input or scoreboard hardware and is unavailable on Android.");
            }
            checkArgument(argument);
        }
    }

    /** Returns argv after the executable name; SDL supplies argv[0]. */
    public String[] arguments(File home) throws IOException {
        return arguments(home, home);
    }

    public String[] arguments(File home, File stateHome) throws IOException {
        validateSettings();
        File root = home.getCanonicalFile();
        if (!root.isDirectory()) {
            throw new IOException("Game storage is unavailable. Choose the game folder first.");
        }
        File frames = resolveFile(root, framefile, "framefile");
        validateFramefile(root, frames);

        List<String> args = new ArrayList<>();
        args.add(game);
        args.add("vldp");
        args.add("-homedir");
        args.add(stateHome.getCanonicalPath());
        args.add("-romdir");
        args.add(new File(root, "roms").getPath());
        args.add("-ramdir");
        args.add(new File(stateHome, "ram").getCanonicalPath());
        args.add("-datadir");
        args.add(root.getPath());
        args.add("-fullscreen");
        args.add("-nosplash");
        args.add("-nomanymouse");
        args.add("-gamepad");
        args.add("-framefile");
        args.add(frames.getPath());
        if (game.equals("singe")) {
            File lua = resolveFile(root, script, "Singe script or ZIP package");
            args.add(script.toLowerCase(Locale.ROOT).endsWith(".zip") ? "-zlua" : "-script");
            args.add(lua.getPath());
        }
        List<String> inherited = new ArrayList<>(splitArguments(extraArguments));
        // Lair/Ace otherwise fall back to their original overlay scoreboard.
        if (scoreLayout == SCORE_OFF && supportsScore(game) && !game.equals("lair2") && !game.equals("tq"))
            args.add("-noscoreboard");
        if (scoreLayout != SCORE_OFF && supportsScore(game, inherited)) {
            args.add("-scorebezel");
            if (supportsScorePlacement(game)) {
                args.add("-scorebezel_layout");
                args.add(SCORE_LAYOUTS[scoreLayout].toLowerCase(Locale.ROOT));
            }
            // Original Space Ace dedicated bezel and live skill lamps. Respect
            // an explicitly supplied alternative native annunciator layout.
            if (Arrays.asList("ace", "ace_a", "ace_a2", "sae").contains(game) &&
                    inherited.stream().noneMatch(option -> option.equalsIgnoreCase("-annunbezel") ||
                            option.equalsIgnoreCase("-dedannunbezel") || option.equalsIgnoreCase("-annunlamps")))
                args.add("-dedannunbezel");
        }
        inherited.removeIf(option -> option.equalsIgnoreCase("-nosplash"));
        args.addAll(GameDifficulty.arguments(game, difficulty, skill, inherited));
        for (String argument : args) checkArgument(argument);
        return args.toArray(new String[0]);
    }

    private static void checkArgument(String argument) {
        // Some upstream game-specific parsers still use 400-byte argument buffers.
        if (argument.isEmpty() || argument.indexOf('\0') >= 0
                || argument.getBytes(StandardCharsets.UTF_8).length > 398) {
            throw new IllegalArgumentException("A launch argument is empty or too long. "
                    + "Use shorter folder names and arguments (at most 398 UTF-8 bytes each).");
        }
    }

    public static File resolveFile(File home, String relativePath, String label) throws IOException {
        if (relativePath == null || relativePath.trim().isEmpty()) {
            throw new IllegalArgumentException("Choose a " + label + ".");
        }
        if (relativePath.indexOf('\0') >= 0 || relativePath.startsWith("content:")) {
            throw new IllegalArgumentException("Choose a filesystem folder first, then choose its " + label + ".");
        }
        if (new File(relativePath).isAbsolute() || relativePath.matches("^[A-Za-z]:.*")) {
            throw new IllegalArgumentException("Use a path inside the selected game folder, "
                    + "for example vldp/lair/lair.txt.");
        }
        File root = home.getCanonicalFile();
        File result = new File(root, relativePath).getCanonicalFile();
        requireInside(root, result);
        if (!result.isFile() || !result.canRead()) {
            throw new IOException("Cannot read " + label + ": " + relativePath
                    + ". Import its folder or use Browse to select the file.");
        }
        return result;
    }

    public static void requireInside(File root, File file) throws IOException {
        relativePath(root, file);
    }

    /** Canonical, contained relative path without the API-26 java.nio.file API. */
    public static String relativePath(File root, File file) throws IOException {
        String base = root.getCanonicalPath();
        String path = file.getCanonicalPath();
        if (path.equals(base)) return "";
        String prefix = base.endsWith(File.separator) ? base : base + File.separator;
        if (!path.startsWith(prefix)) {
            throw new IOException("The selected path leaves the game's selected folder.");
        }
        return path.substring(prefix.length());
    }

    /** Reject the common desktop-path mistakes before entering native code. */
    private static void validateFramefile(File home, File framefile) throws IOException {
        if (framefile.length() > 4 * 1024 * 1024) {
            throw new IOException("This framefile is unusually large. Choose the small text "
                    + "file that maps frame numbers to MPEG files, not the video itself.");
        }
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                new FileInputStream(framefile), StandardCharsets.UTF_8))) {
            String directory = reader.readLine();
            if (directory == null || directory.trim().isEmpty()) {
                throw new IOException("The framefile's first line must name the video folder. "
                        + "Use ./ when the video is beside the framefile.");
            }
            if (directory.charAt(0) == '\ufeff') {
                throw new IOException("Save the framefile as UTF-8 without a byte-order mark (BOM).");
            }
            directory = directory.replace('\\', '/');
            if (directory.matches("^[A-Za-z]:.*")) {
                throw new IOException("The framefile contains a Windows video path. Change its "
                        + "first line to a relative folder, such as ./, and select it again.");
            }
            File media = new File(directory);
            if (!media.isAbsolute()) media = new File(framefile.getParentFile(), directory);
            media = media.getCanonicalFile();
            requireInside(home, media);
            if (!media.isDirectory()) {
                throw new IOException("The video folder named by the framefile is missing: "
                        + directory + ". Import the complete game folder with its videos.");
            }

            String line;
            int lineNumber = 1;
            boolean foundFrame = false;
            while ((line = reader.readLine()) != null) {
                lineNumber++;
                if (line.trim().isEmpty()) continue;
                String[] words = line.trim().split("\\s+", 3);
                if (words.length < 2 || !words[0].matches("[+-]?\\d+")) {
                    throw new IOException("Framefile line " + lineNumber
                            + " must contain a frame number followed by an MPEG filename.");
                }
                try {
                    Integer.parseInt(words[0]);
                } catch (NumberFormatException error) {
                    throw new IOException("Frame number is out of range on line " + lineNumber + ".");
                }
                File video = new File(media, words[1]).getCanonicalFile();
                requireInside(home, video);
                if (!video.isFile()) {
                    throw new IOException("Video missing on framefile line " + lineNumber + ": "
                            + words[1] + ". Names are case-sensitive; place the matching MPEG file in that folder.");
                }
                foundFrame = true;
            }
            if (!foundFrame) throw new IOException("The framefile has no frame-to-video entries.");
        }
    }

    /**
     * Tokenize quoted arguments without invoking a shell or expanding variables.
     * Backslash escapes the next character outside single quotes.
     */
    public static List<String> splitArguments(String input) {
        List<String> result = new ArrayList<>();
        if (input == null || input.isEmpty()) return result;
        if (input.length() > 8192) {
            throw new IllegalArgumentException("Extra arguments are too long (maximum 8192 characters).");
        }
        StringBuilder word = new StringBuilder();
        char quote = 0;
        boolean escaped = false;
        boolean started = false;
        for (int i = 0; i < input.length(); i++) {
            char ch = input.charAt(i);
            if (ch == 0) throw new IllegalArgumentException("Arguments cannot contain NUL characters.");
            if (escaped) {
                word.append(ch);
                escaped = false;
                started = true;
            } else if (ch == '\\' && quote != '\'') {
                escaped = true;
                started = true;
            } else if (quote != 0) {
                if (ch == quote) quote = 0;
                else word.append(ch);
            } else if (ch == '\'' || ch == '"') {
                quote = ch;
                started = true;
            } else if (Character.isWhitespace(ch)) {
                if (started) {
                    addWord(result, word);
                    started = false;
                }
            } else {
                word.append(ch);
                started = true;
            }
        }
        if (escaped) throw new IllegalArgumentException("Extra arguments end with an unfinished backslash escape.");
        if (quote != 0) throw new IllegalArgumentException("Close the quotation mark in extra arguments.");
        if (started) addWord(result, word);
        return result;
    }

    private static void addWord(List<String> result, StringBuilder word) {
        if (word.length() == 0) throw new IllegalArgumentException("An empty quoted argument is not supported.");
        result.add(word.toString());
        word.setLength(0);
        if (result.size() > 128) throw new IllegalArgumentException("Use at most 128 extra arguments.");
    }
}
