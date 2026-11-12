/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;
import java.util.ArrayDeque;
import java.util.Arrays;
final class HypseusActivity {
    static final boolean[] held = new boolean[13];
    static final ArrayDeque<Long> events = new ArrayDeque<>();
    static long guidance;
    static int credits;
    static boolean started, automation;
    static void reset() {
        Arrays.fill(held, false); events.clear(); guidance = 0;
        credits = 0; started = automation = false;
    }
    static void nativeArcadeInput(int action, boolean down) {
        if (action == 7 && down && !held[action]) credits++;
        held[action] = down;
    }
    static boolean nativeEmulatorReady() { return true; }
    static int nativeWatchCredits() { return credits; }
    static boolean nativeWatchCoinPending() { return false; }
    static boolean nativeWatchGameStarted() { return started; }
    static void nativeSetWatchAutomation(boolean enabled) { automation = enabled; }
    static long nativeGuidance() { return guidance; }
    static long nativeTakeWatchMove() { return events.isEmpty() ? 0 : events.removeFirst(); }
    static void nativeRequestCurrentWatchMove() {
        if ((guidance & 256) != 0) events.addLast(guidance & ~256L);
    }
}
