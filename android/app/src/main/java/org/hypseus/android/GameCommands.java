/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

/** Imports argument lists once; native Hypseus remains the option parser. */
final class GameCommands {
    static String read(File root, File framefile, String game) throws IOException {
        String name = framefile.getName();
        int dot = name.lastIndexOf('.');
        File file = new File(framefile.getParentFile(),
                (dot < 0 ? name : name.substring(0, dot)) + ".commands");
        if (!file.exists()) return LaunchConfig.supportsFastBoot(game) ? "-fastboot" : "";
        LaunchConfig.requireInside(root.getCanonicalFile(), file.getCanonicalFile());
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (FileInputStream input = new FileInputStream(file)) {
            byte[] buffer = new byte[1024];
            int n;
            while ((n = input.read(buffer)) != -1) {
                if (bytes.size() + n > 8192) throw new IOException("Command file exceeds 8192 bytes");
                bytes.write(buffer, 0, n);
            }
        }
        String text = new String(bytes.toByteArray(), StandardCharsets.UTF_8);
        if (text.startsWith("\ufeff")) text = text.substring(1);
        // Strip comments only outside quotes; keep quoted # and escaped quotes intact.
        StringBuilder clean = new StringBuilder();
        char quote = 0;
        boolean escape = false, comment = false;
        for (char c : text.replace("\\\r\n", "").replace("\\\n", "").toCharArray()) {
            if (comment) { if (c != '\n' && c != '\r') continue; comment = false; }
            if (!escape && quote == 0 && c == '#') { comment = true; continue; }
            clean.append(c);
            if (escape) { escape = false; continue; }
            if (c == '\\' && quote != '\'') { escape = true; continue; }
            if (c == quote) quote = 0;
            else if (quote == 0 && (c == '\'' || c == '"')) quote = c;
        }
        List<String> input = LaunchConfig.splitArguments(clean.toString());
        List<String> kept = new ArrayList<>();
        // Paths, screen geometry and controller configuration belong to Android.
        List<String> oneValue = Arrays.asList("-homedir", "-datadir", "-romdir", "-ramdir",
                "-framefile", "-script", "-zlua", "-keymapfile", "-config", "-x", "-y",
                "-rotate", "-useoverlaysb", "-scanline_shunt", "-scanline_alpha");
        List<String> flags = Arrays.asList("-scorebezel", "-fullscreen",
                "-gamepad", "-nomanymouse", "-nojoystick", "-tiphat", "-openhat");
        for (int i = 0; i < input.size(); i++) {
            String value = input.get(i), option = value.toLowerCase(Locale.ROOT);
            if (option.equals("-gamepad_reorder"))
                throw new IOException("-gamepad_reorder is unavailable; use Configure controller");
            if (oneValue.contains(option)) {
                if (++i >= input.size() || input.get(i).startsWith("-") &&
                        !input.get(i).matches("-\\d+(\\.\\d+)?"))
                    throw new IOException("Missing value for " + option);
            } else if (!flags.contains(option)) kept.add(value);
        }
        // With a commands file, absence of fastboot means off. Without one use our default.
        return new VideoOptions(kept).arguments(kept);
    }
}
