/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

import android.content.Context;
import android.content.SharedPreferences;

/** One installation-wide directory and controller configuration, separate from games. */
final class SetupSettings {
    private final SharedPreferences preferences;

    SetupSettings(Context context) {
        preferences = context.getSharedPreferences("setup", Context.MODE_PRIVATE);
    }

    String directory() { return preferences.getString("directory", ""); }
    String encodedControls() { return preferences.getString("controls", ""); }
    ControlMap controls() { return ControlMap.decode(encodedControls()); }
    boolean canPlay() { return controls().canPlay(BuildConfig.ARCADE, touchControls()); }
    boolean touchControls() { return preferences.getBoolean("touch", true); }

    // Setup must be on disk before a new emulator process or activity can use it.
    @android.annotation.SuppressLint("ApplySharedPref")
    boolean saveDirectory(String path) {
        return preferences.edit().putString("directory", path).commit();
    }

    @android.annotation.SuppressLint("ApplySharedPref")
    boolean saveControls(ControlMap controls) {
        return controls.isComplete()
                && preferences.edit().putString("controls", controls.encode()).commit();
    }

    @android.annotation.SuppressLint("ApplySharedPref")
    boolean clearControls() { return preferences.edit().remove("controls").commit(); }

    @android.annotation.SuppressLint("ApplySharedPref")
    boolean saveTouchControls(boolean enabled) {
        return preferences.edit().putBoolean("touch", enabled).commit();
    }
}
