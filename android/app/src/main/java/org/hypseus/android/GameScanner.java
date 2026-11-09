/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import java.util.function.BooleanSupplier;

/** Read-only discovery; never follows links outside the source or reads video payloads. */
final class GameScanner {
    static final class Result {
        final List<LaunchConfig> games = new ArrayList<>();
        int skipped;
        boolean limited;
        final List<String> commandErrors = new ArrayList<>();
    }
    static Result scan(File folder, List<LaunchConfig> saved, BooleanSupplier cancelled) throws IOException {
        File root = folder.getCanonicalFile();
        Result result = new Result();
        if (!root.isDirectory() || !root.canRead()) throw new IOException("Game folder is unavailable.");
        Set<String> visited = new HashSet<>(), discovered = new HashSet<>();
        // Explicit saved entries may use nonstandard framefile extensions.
        for (LaunchConfig config : saved) {
            if (cancelled.getAsBoolean()) return result;
            try {
                config.arguments(root);
                if (discovered.add(config.framefile+"\n"+config.script)) result.games.add(config);
            } catch (IOException | IllegalArgumentException unavailable) { /* Not on this card. */ }
        }
        List<File> pending = new ArrayList<>();
        pending.add(root);
        int count = 0;
        while (!pending.isEmpty() && !cancelled.getAsBoolean()) {
            File dir = pending.remove(pending.size()-1).getCanonicalFile();
            try { LaunchConfig.requireInside(root, dir); } catch (IOException outside) { continue; }
            if (!visited.add(dir.getPath())) continue;
            File[] files = dir.listFiles();
            if (files == null) { result.skipped++; continue; }
            Arrays.sort(files, Comparator.comparing(File::getName));
            for (File file : files) {
                if (cancelled.getAsBoolean()) return result;
                if (++count > 40000) { result.limited = true; pending.clear(); break; }
                if (file.getName().startsWith(".")) continue;
                if (file.isDirectory()) {
                    if (!file.getName().equalsIgnoreCase("roms")) pending.add(file);
                    continue;
                }
                String name = file.getName().toLowerCase(Locale.ROOT);
                if (!name.endsWith(".txt") && !name.endsWith(".frame") && !name.endsWith(".framefile")) continue;
                try {
                    String path = LaunchConfig.relativePath(root, file);
                    String game = LaunchConfig.inferGame(path);
                    String script = "";
                    // Keep explicit saved revisions and scripts, including nonstandard layouts.
                    LaunchConfig selected = null;
                    for (LaunchConfig old : saved) if (old.framefile.equals(path)) { selected = old; break; }
                    if (selected == null) {
                        if (game.isEmpty()) { result.skipped++; continue; }
                        if (game.equals("singe")) {
                            File chosen = null;
                            String stem = name.replaceFirst("[.][^.]+$", "");
                            for (String suffix : new String[]{".singe", ".zip"}) {
                                File candidate = new File(dir, stem + suffix);
                                if (candidate.isFile()) { chosen = candidate; break; }
                            }
                            if (chosen == null) {
                                for (File candidate : files) if (candidate.isFile() && candidate.getName().toLowerCase(Locale.ROOT).endsWith(".singe")) {
                                    if (chosen != null) { chosen = null; break; }
                                    chosen = candidate;
                                }
                            }
                            if (chosen == null) { result.skipped++; continue; }
                            script = LaunchConfig.relativePath(root, chosen);
                        }
                        String id = UUID.nameUUIDFromBytes((path+"\n"+script).getBytes(StandardCharsets.UTF_8)).toString();
                        String commands;
                        try {
                            commands = GameCommands.read(root, file, game);
                            new LaunchConfig(id, title(game, path), game, path, script, commands).validateSettings();
                        }
                        catch (IOException | IllegalArgumentException invalid) {
                            if (result.commandErrors.size() < 5) result.commandErrors.add(path + ": " + invalid.getMessage());
                            continue;
                        }
                        selected = new LaunchConfig(id, title(game, path), game, path, script, commands);
                    }
                    selected.arguments(root); // validates framefile/media/script paths, without decoding/copying
                    if (discovered.add(selected.framefile+"\n"+selected.script)) result.games.add(selected);
                } catch (IOException | IllegalArgumentException invalid) { result.skipped++; }
            }
        }
        result.games.sort(Comparator.comparing((LaunchConfig c) -> c.name, String.CASE_INSENSITIVE_ORDER).thenComparing(c -> c.framefile));
        return result;
    }
    private static String title(String game, String path) {
        String title;
        switch (game) {
            case "dle21": title="Dragon's Lair (Enhanced 2.1)"; break;
            case "lair": title="Dragon's Lair"; break;
            case "lair2": title="Dragon's Lair II"; break;
            case "ace": title="Space Ace"; break;
            default: title=game.equals("singe") && new File(path).getParentFile()!=null ? new File(path).getParentFile().getName() : game;
        }
        return title + " · " + path;
    }
}
