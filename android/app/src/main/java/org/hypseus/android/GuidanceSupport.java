/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

import java.util.Arrays;
import java.util.List;

/** Capabilities of the bundled ROM guidance; Singe owns its own Lua options. */
final class GuidanceSupport {
    final boolean visual;
    final boolean cue;
    final boolean scriptControlled;

    private GuidanceSupport(boolean visual, boolean cue, boolean scriptControlled) {
        this.visual = visual;
        this.cue = cue;
        this.scriptControlled = scriptControlled;
    }

    static GuidanceSupport forArguments(String[] arguments) {
        return arguments == null || arguments.length == 0
                ? forGame("", java.util.Collections.emptyList())
                : forGame(arguments[0], Arrays.asList(arguments).subList(1, arguments.length));
    }

    static GuidanceSupport forGame(String game, List<String> options) {
        if ("singe".equals(game)) return new GuidanceSupport(false, false, true);
        boolean visual = "dle21".equals(game) || "ace".equals(game) || "sae".equals(game)
                || game.matches("lair_[a-f]") || "lair_ita".equals(game) || "laireuro".equals(game) || "lair2".equals(game);
        String supportedVersion = "lair2".equals(game) ? "6" : "lair_ita".equals(game) ? "2" : "1";
        // Reject unsupported or ambiguous revision selections, including repeated flags.
        for (int i = 0; i < options.size(); i++) {
            if ("-version".equalsIgnoreCase(options.get(i))) {
                if (++i == options.size() || !supportedVersion.equals(options.get(i))) visual = false;
            }
        }
        return new GuidanceSupport(visual, visual && !"lair2".equals(game), false);
    }
}
