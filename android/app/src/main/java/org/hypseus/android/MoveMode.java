/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

/** Shared launcher/JNI values for the two bundled move policies. */
final class MoveMode {
    static final int OFF = 0;
    static final int MAX_SCORE = 1;
    static final int FEWEST_MOVES = 2;
    static final String[] LABELS = {"Off", "Max score", "Fewest moves"};

    private MoveMode() { }

    static int selected(int mode) {
        return mode >= OFF && mode <= FEWEST_MOVES ? mode : OFF;
    }

}
