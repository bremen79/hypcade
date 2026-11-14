/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
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
        Handler.advanceTo(1992); released();
        check(HypseusActivity.credits == 0, "Coin inserted before the initial two-second delay");
        Handler.advanceTo(2112); HypseusActivity.started = true; Handler.advanceTo(2128);
        check(HypseusActivity.automation, "Automation did not start after the ROM acknowledged Start");
        return controller;
    }
    private static void released() {
        for (boolean held : HypseusActivity.held) check(!held, "An input remains held");
    }
    public static void main(String[] args) {
        Handler.reset(); HypseusActivity.reset(); HypseusActivity.coinsPerCredit = 3;
        WatchModeController multiCoin = new WatchModeController(); multiCoin.start();
        Handler.advanceTo(6000);
        check(HypseusActivity.credits == 0 && HypseusActivity.startPresses == 0,
                "Start was pressed without enough coins for a credit");
        Handler.advanceTo(10000);
        check(HypseusActivity.credits == 1 && HypseusActivity.coins == 3 && HypseusActivity.startPresses > 0,
                "Shared startup does not support three coins per credit");
        check(!HypseusActivity.automation, "Automation started before the ROM acknowledged Start");
        HypseusActivity.started = true; Handler.advanceTo(10008);
        check(HypseusActivity.automation, "Delayed Start acknowledgment was lost");
        multiCoin.stop(); released();

        Handler.reset(); HypseusActivity.reset();
        WatchModeController waiting = new WatchModeController(); waiting.start();
        Handler.advanceTo(2112); HypseusActivity.credits = 0; Handler.advanceTo(2128);
        check(!HypseusActivity.automation, "Credit reset was mistaken for a started game");
        Handler.advanceTo(5200);
        check(HypseusActivity.held[8], "Start was not retried after a credit reset");
        waiting.stop(); released();

        WatchModeController controller = start();
        HypseusActivity.guidance = (2L << 32) | 256 | 2;
        HypseusActivity.events.addLast((1L << 32) | 1);
        Handler.advanceTo(2136); released(); controller.stop();

        controller = start();
        HypseusActivity.guidance = (1L << 32) | 1;
        HypseusActivity.events.addLast((1L << 32) | 1);
        Handler.advanceTo(2136); released(); controller.stop();

        controller = start();
        HypseusActivity.guidance = (1L << 32) | 256 | 1;
        HypseusActivity.events.addLast((1L << 32) | 1);
        Handler.advanceTo(2136); check(HypseusActivity.held[0], "Live UP was not pressed");
        controller.setLifecyclePaused(true); released();
        check(!HypseusActivity.automation, "Automation continues in the background");
        controller.setLifecyclePaused(false); Handler.advanceTo(2136);
        check(HypseusActivity.held[0], "Current move was not requested after resume");
        controller.stop(); released();
        System.out.println("Watch Mode stale-event and lifecycle checks passed");
    }
}
