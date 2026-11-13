/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
// SPDX-License-Identifier: GPL-3.0-or-later
package org.hypseus.android;
import android.media.ToneGenerator;
import android.os.Handler;

public final class MoveGuidanceTest {
    private static void check(boolean ok) { if (!ok) throw new AssertionError(); }
    public static void main(String[] args) {
        Handler.reset(); HypseusActivity.reset();
        MoveGuidance guidance = new MoveGuidance();
        guidance.start();
        HypseusActivity.guidance = 1; // Preview: native text is also hidden.
        Handler.advanceTo(32); check(ToneGenerator.beeps == 0);
        HypseusActivity.guidance = (1L << 32) | 256 | 1;
        Handler.advanceTo(48); check(ToneGenerator.beeps == 1);
        Handler.advanceTo(160); check(ToneGenerator.beeps == 1);
        HypseusActivity.guidance = (1L << 32); // Closed window.
        Handler.advanceTo(176); check(ToneGenerator.beeps == 1);
        HypseusActivity.guidance = (2L << 32) | 256 | 8;
        Handler.advanceTo(192); check(ToneGenerator.beeps == 2);
        guidance.stop();
        HypseusActivity.guidance = (3L << 32) | 256 | 16;
        Handler.advanceTo(224); check(ToneGenerator.beeps == 2);
        guidance.close();
        System.out.println("Move audio: no preview beep, one beep per ready event, stop cancels polling");
    }
}
