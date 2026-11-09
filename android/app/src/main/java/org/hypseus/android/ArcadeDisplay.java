/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

/** Native cabinet resolution with fixed landscape orientation for every game launch. */
final class ArcadeDisplay {
    static String[] arguments(String[] source, int width, int height) {
        if (source.length == 1 && source[0].equals("--android-smoke-test")) return source;
        List<String> result = new ArrayList<>();
        for (int i = 0; i < source.length; ++i) {
            String option = source[i].toLowerCase(Locale.ROOT);
            if (option.equals("-rotate") || option.equals("-x") || option.equals("-y")) {
                if (i + 1 < source.length) ++i;
            } else result.add(source[i]);
        }
        if (width <= 0 || height <= 0) { width=960; height=720; }
        result.addAll(Arrays.asList("-x", Integer.toString(Math.max(width,height)),
                "-y", Integer.toString(Math.min(width,height)), "-rotate", "0",
                "-fullscreen", "-preserve_aspect_ratio"));
        return result.toArray(new String[0]);
    }
}
