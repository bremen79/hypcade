/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Launcher-owned options; preserve unrelated inherited arguments and their quoting. */
final class VideoOptions {
    private static final Set<String> OWNED = new HashSet<>(Arrays.asList(
            "-showfps", "-fastboot", "-nosplash", "-linear_scale", "-scanlines", "-novsync"));
    boolean fastBoot, smooth, scanlines, showFps;
    boolean vsync = true;
    VideoOptions(List<String> options) {
        for (String option : options) switch (option.toLowerCase(Locale.ROOT)) {
            case "-showfps": showFps=true; break;
            case "-fastboot": fastBoot=true; break;
            case "-linear_scale": smooth=true; break;
            case "-scanlines": scanlines=true; break;
            case "-novsync": vsync=false; break;
            default: break;
        }
    }
    String arguments(List<String> inherited) {
        List<String> options=new ArrayList<>();
        for(String value:inherited) if(!OWNED.contains(value.toLowerCase(Locale.ROOT))) options.add(value);
        if(showFps) options.add("-showfps");
        if(fastBoot) options.add("-fastboot");
        if(smooth) options.add("-linear_scale");
        if(scanlines) options.add("-scanlines");
        if(!vsync) options.add("-novsync");
        StringBuilder result=new StringBuilder();
        for(String value:options) {
            if(result.length()>0) result.append(' ');
            result.append('"').append(value.replace("\\","\\\\").replace("\"","\\\"")).append('"');
        }
        return result.toString();
    }
}
