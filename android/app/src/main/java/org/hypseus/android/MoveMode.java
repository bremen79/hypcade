/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

/** Shared launcher/JNI values; availability comes from the generated catalog. */
final class MoveMode {
    static final int OFF = 0;
    static final int MAX_SCORE = 1;
    static final int FEWEST_MOVES = 2;
    static final String[] LABELS = {"Off", "Max score", "Fewest moves"};
    private static final String[] ROM_LABELS = {"Off", "On"};

    private MoveMode() { }

    static int selected(int mode) {
        return mode >= OFF && mode <= FEWEST_MOVES ? mode : OFF;
    }

    static String[] labels(String game) {
        return MovePolicyCatalog.hasFewest(game) ? LABELS : ROM_LABELS;
    }

    static int selected(String game, int mode) {
        int valid = selected(mode);
        return !MovePolicyCatalog.hasFewest(game) && valid != OFF ? MAX_SCORE : valid;
    }

}
