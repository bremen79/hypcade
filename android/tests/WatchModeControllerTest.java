/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;
import android.os.Handler;
public final class WatchModeControllerTest {
    private WatchModeControllerTest() {}
    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
    private static WatchModeController start() {
        Handler.reset(); HypseusActivity.reset();
        WatchModeController controller = new WatchModeController(); controller.start();
        Handler.advanceTo(112); HypseusActivity.started = true; Handler.advanceTo(128);
        check(HypseusActivity.automation, "Automation did not start after the ROM acknowledged Start");
        return controller;
    }
    private static void released() {
        for (boolean held : HypseusActivity.held) check(!held, "An input remains held");
    }
    public static void main(String[] args) {
        WatchModeController controller = start();
        HypseusActivity.guidance = (2L << 32) | 256 | 2;
        HypseusActivity.events.addLast((1L << 32) | 1);
        Handler.advanceTo(136); released(); controller.stop();

        controller = start();
        HypseusActivity.guidance = (1L << 32) | 1;
        HypseusActivity.events.addLast((1L << 32) | 1);
        Handler.advanceTo(136); released(); controller.stop();

        controller = start();
        HypseusActivity.guidance = (1L << 32) | 256 | 1;
        HypseusActivity.events.addLast((1L << 32) | 1);
        Handler.advanceTo(136); check(HypseusActivity.held[0], "Live UP was not pressed");
        controller.setLifecyclePaused(true); released();
        check(!HypseusActivity.automation, "Automation continues in the background");
        controller.setLifecyclePaused(false); Handler.advanceTo(136);
        check(HypseusActivity.held[0], "Current move was not requested after resume");
        controller.stop(); released();
        System.out.println("Watch Mode stale-event and lifecycle checks passed");
    }
}
