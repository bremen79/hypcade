/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.zip.GZIPInputStream;

/** A small catalog of established DIP layouts, plus DL2's EEPROM setting. */
final class GameDifficulty {
    static final String[] SKILLS = {"Cadet", "Captain", "Ace"};
    private static final String[] UNAVAILABLE = {"Unavailable"};
    private static final Map<String, Dip> DIPS = new HashMap<>();

    private static final class Dip {
        final String[] labels;
        final int[] defaults, masks;
        final int[][] values;
        Dip(String[] labels, int a, int b, int maskA, int maskB, int[][] values) {
            this.labels = labels; this.defaults = new int[]{a, b};
            this.masks = new int[]{maskA, maskB}; this.values = values;
        }
    }

    static {
        // Values are raw driver bytes. Native -bank arguments invert them.
        // US Dragon's Lair: MAME cinematronics/dlair.cpp, DSW1/DSW2.
        String[] lairLabels = {"Easy", "Hard", "Increase after 5 scenes", "Increase after 9 scenes"};
        int[][] lairValues = {{4, 0x10}, {4, 0}, {0, 0}, {0, 0x10}};
        register("lair lair_e lair_f", new Dip(
                lairLabels, 0x22, 0xd8, 4, 0x90, lairValues));
        register("lair_a lair_b lair_c lair_d", new Dip(
                lairLabels, 0, 8, 4, 0x90, lairValues));
        // Original Cinematronics manual, Appendix C: A2 and A3, active low.
        register("ace ace_a ace_a2", new Dip(
                new String[]{"After 5 episodes · slow", "After 5 episodes · fast", "After 3 episodes · slow", "After 3 episodes · fast"},
                0x3d, 0xfe, 0x0c, 0, new int[][]{{0x0c, 0}, {4, 0}, {8, 0}, {0, 0}}));
        // SAE has a different switch layout (vendor cinematronics/board.c).
        register("sae", new Dip(new String[]{"Easy", "Hard"},
                0x66, 0x98, 0, 0x80, new int[][]{{0, 0x80}, {0, 0}}));
        register("roadblaster", new Dip(new String[]{"Normal", "Hard"},
                0xff, 0xf8, 0, 0x10, new int[][]{{0, 0x10}, {0, 0}}));
        String[] labels = new String[16]; int[][] values = new int[16][];
        for (int i = 0; i < 16; i++) {
            labels[i] = "Level " + i + (i == 0 ? " (easiest)" : i == 15 ? " (hardest)" : "");
            values[i] = new int[]{15 - i, 0};
        }
        register("cliff", new Dip(labels, 0xfd, 0xff, 15, 0, values));
        register("cliffalt cliffalt2", new Dip(labels, 0xff, 0xff, 15, 0, values));
    }

    private static void register(String games, Dip layout) {
        for (String game : games.split(" ")) DIPS.put(game, layout);
    }

    static boolean spaceAce(String game) {
        return Arrays.asList("ace", "ace_a", "ace_a2", "sae").contains(game);
    }
    static int selectedSkill(int value) { return value >= 0 && value < SKILLS.length ? value : 0; }
    static int startSkill(String game, int value) { return spaceAce(game) ? selectedSkill(value) + 1 : 0; }

    static String[] choices(String game) {
        if (game.equals("lair2")) return new String[]{"Level 0 (easiest)", "Level 1", "Level 2", "Level 3", "Level 4 (hardest)"};
        Dip layout = DIPS.get(game);
        return layout == null ? UNAVAILABLE : layout.labels;
    }
    static String[] choices(String game, List<String> options) {
        return game.equals("lair2") && !LaunchConfig.supportsScore(game, options) ? UNAVAILABLE : choices(game);
    }
    static int selected(String game, int value) {
        return value >= 0 && value < choices(game).length ? value : importedSelection(game, java.util.Collections.emptyList());
    }
    static String unavailable(String game) {
        if (game.equals("dle21")) return "Difficulty — DLE 2.1 has no difficulty settings";
        if (game.equals("lair2")) return "Difficulty — requires DL2 US 3.19";
        if (game.equals("ace91") || game.equals("singe")) return "Difficulty — use Game options / Service in the game";
        return "Difficulty — unavailable for this ROM";
    }

    static int importedSelection(String game, List<String> options) {
        if (game.equals("lair2")) {
            int result = -1;
            if (choices(game, options).length > 1)
                for (int i = 0; i + 1 < options.size(); i++)
                    if (options.get(i).equalsIgnoreCase("-preset") && options.get(i + 1).matches("[0-4]"))
                        result = Integer.parseInt(options.get(++i));
            return result;
        }
        Dip layout = DIPS.get(game);
        if (layout == null) return 0;
        int[] raw = rawBanks(options, layout.defaults);
        // B8 forces Easy in either Dragon's Lair difficulty mode.
        if (layout.labels == DIPS.get("lair").labels && (raw[1] & 0x80) != 0) return 0;
        for (int i = 0; i < layout.values.length; i++) {
            int[] value = layout.values[i];
            if ((raw[0] & layout.masks[0]) == value[0] && (raw[1] & layout.masks[1]) == value[1]) return i;
        }
        return 0;
    }

    static int readDl2Level(File stateHome) throws IOException {
        File file = new File(stateHome, "ram/lair2_319.gz");
        if (!file.exists()) return 0; // US 3.19 factory difficulty
        byte[] data = new byte[128];
        try (GZIPInputStream input = new GZIPInputStream(new FileInputStream(file))) {
            int used = 0;
            while (used < data.length) {
                int count = input.read(data, used, data.length - used);
                if (count < 0) return 0;
                used += count;
            }
        }
        int level = (data[28] & 255) | (data[29] & 255) << 8;
        return (data[0] & 255) == 0x41 && (data[1] & 255) == 0x12 && level <= 4 ? level : 0;
    }

    static List<String> arguments(String game, int selection, List<String> inherited) {
        List<String> result = new ArrayList<>(inherited);
        int level = selected(game, selection);
        if (game.equals("lair2")) {
            if (level < 0) return result;
            if (choices(game, inherited).length <= 1)
                throw new IllegalArgumentException("DL2 difficulty requires the US 3.19 ROM (-version 6).");
            result.add("-preset"); result.add(Integer.toString(level));
        } else {
            Dip layout = DIPS.get(game);
            if (layout == null) return result;
            int[] raw = rawBanks(inherited, layout.defaults);
            for (int bank = 0; bank < 2; bank++) if (layout.masks[bank] != 0) {
                int value = ((raw[bank] & ~layout.masks[bank]) | layout.values[level][bank]) ^ 255;
                result.add("-bank"); result.add(Integer.toString(bank));
                result.add(String.format(java.util.Locale.ROOT, "%8s", Integer.toBinaryString(value)).replace(' ', '0'));
            }
        }
        return result;
    }

    private static int[] rawBanks(List<String> args, int[] defaults) {
        int[] raw = defaults.clone();
        for (int i = 0; i < args.size(); i++) {
            if (!args.get(i).equalsIgnoreCase("-bank")) continue;
            if (i + 2 >= args.size() || !args.get(i + 1).matches("[0-9]+") || !args.get(i + 2).matches("[01]{1,8}"))
                throw new IllegalArgumentException("Invalid -bank setting: expected a bank number and one to eight binary digits.");
            int bank = Integer.parseInt(args.get(i + 1));
            if (bank < raw.length) raw[bank] = Integer.parseInt(args.get(i + 2), 2) ^ 255;
            i += 2;
        }
        return raw;
    }
}
