/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Log;

import java.util.ArrayDeque;

/** Replays only native score-verified move events through Hypseus's logical input API. */
final class WatchModeController {
    private static final int COIN = 7;
    private static final int START1 = 8;
    private static final long POLL_MS = 8;
    private static final long KEY_HOLD_MS = 100;
    private static final long COIN_RETRY_MS = 2000;
    private static final long START_RETRY_MS = 3000;
    private static final int WAIT_READY = 0;
    private static final int COIN_DOWN = 1;
    private static final int WAIT_CREDIT = 2;
    private static final int START_DOWN = 3;
    private static final int WAIT_START_ACK = 4;
    private static final int PLAYING = 5;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ArrayDeque<Long> moves = new ArrayDeque<>();
    private final Runnable tick = this::run;
    private boolean running;
    private boolean userPaused;
    private boolean lifecyclePaused;
    private boolean coinHeld;
    private boolean startHeld;
    private boolean moveHeld;
    private int phase = WAIT_READY;
    private int heldActions;
    private int creditsBeforeCoin = -1;
    private int creditsBeforeStart = -1;
    private long deadline;
    private long pauseStarted;
    private long tracedGuidance = Long.MIN_VALUE;

    void start() {
        if (running) return;
        running = true;
        phase = WAIT_READY;
        creditsBeforeCoin = -1;
        creditsBeforeStart = -1;
        tracedGuidance = Long.MIN_VALUE;
        handler.post(tick);
    }

    void toggleUserPause() {
        setUserPaused(!userPaused);
    }

    private void setUserPaused(boolean paused) {
        if (userPaused == paused) return;
        userPaused = paused;
        updatePauseState();
    }

    void setLifecyclePaused(boolean paused) {
        if (lifecyclePaused == paused) return;
        lifecyclePaused = paused;
        updatePauseState();
    }

    private void updatePauseState() {
        long now = SystemClock.uptimeMillis();
        boolean paused = userPaused || lifecyclePaused;
        if (paused) {
            pauseStarted = now;
            HypseusActivity.nativeSetWatchAutomation(false);
            moves.clear();
            releaseMove();
            if (coinHeld) {
                send(COIN, false);
                coinHeld = false;
                phase = WAIT_CREDIT;
                deadline = now + COIN_RETRY_MS;
            }
            if (startHeld) {
                send(START1, false);
                startHeld = false;
                deadline = now + 250;
            }
        } else if (running) {
            deadline += Math.max(0, now - pauseStarted);
            if (phase == PLAYING) {
                HypseusActivity.nativeSetWatchAutomation(true);
                HypseusActivity.nativeRequestCurrentWatchMove();
            }
            handler.removeCallbacks(tick);
            handler.post(tick);
        }
    }

    void stop() {
        running = false;
        handler.removeCallbacks(tick);
        HypseusActivity.nativeSetWatchAutomation(false);
        moves.clear();
        releaseAll();
    }

    void close() {
        stop();
    }

    private boolean paused() {
        return userPaused || lifecyclePaused;
    }

    private void send(int action, boolean down) {
        if (BuildConfig.DEBUG) Log.d("HypcadeWatch", "input=" + action + " down=" + down
                + " time=" + SystemClock.uptimeMillis());
        HypseusActivity.nativeArcadeInput(action, down);
    }

    private void releaseMove() {
        if (!moveHeld) return;
        for (int action = 0; action < 5; action++)
            if ((heldActions & (1 << action)) != 0) send(action, false);
        heldActions = 0;
        moveHeld = false;
    }

    private void releaseAll() {
        releaseMove();
        if (coinHeld) { send(COIN, false); coinHeld = false; }
        if (startHeld) { send(START1, false); startHeld = false; }
    }

    private void beginMove(int controls, long now) {
        heldActions = controls & 15;
        if ((controls & 16) != 0) heldActions |= 1 << 4;
        if (heldActions == 0) return;
        for (int action = 0; action < 5; action++)
            if ((heldActions & (1 << action)) != 0) send(action, true);
        moveHeld = true;
        deadline = now + KEY_HOLD_MS;
    }

    private void run() {
        if (!running) return;
        if (paused()) {
            handler.postDelayed(tick, 50);
            return;
        }
        long now = SystemClock.uptimeMillis();
        int previousPhase = phase;
        switch (phase) {
            case WAIT_READY:
                if (!HypseusActivity.nativeEmulatorReady()) break;
                creditsBeforeCoin = HypseusActivity.nativeWatchCredits();
                send(COIN, true);
                coinHeld = true;
                phase = COIN_DOWN;
                deadline = now + KEY_HOLD_MS;
                break;
            case COIN_DOWN:
                if (now >= deadline) {
                    send(COIN, false);
                    coinHeld = false;
                    phase = WAIT_CREDIT;
                    deadline = now + COIN_RETRY_MS;
                }
                break;
            case WAIT_CREDIT:
                {
                    int credits = HypseusActivity.nativeWatchCredits();
                    boolean creditAdded = credits >= 0 &&
                        (creditsBeforeCoin < 0 ? credits > 0 : credits != creditsBeforeCoin || credits == 99);
                    if (creditAdded) {
                        creditsBeforeStart = credits;
                        phase = WAIT_START_ACK;
                        deadline = now + START_RETRY_MS;
                    } else if (now >= deadline) {
                        if (HypseusActivity.nativeWatchCoinPending()) {
                            deadline = now + 500;
                            break;
                        }
                        creditsBeforeCoin = credits;
                        send(COIN, true);
                        coinHeld = true;
                        phase = COIN_DOWN;
                        deadline = now + KEY_HOLD_MS;
                    }
                }
                break;
            case START_DOWN:
                if (!startHeld && now >= deadline) {
                    send(START1, true);
                    startHeld = true;
                    deadline = now + KEY_HOLD_MS;
                } else if (startHeld && now >= deadline) {
                    send(START1, false);
                    startHeld = false;
                    phase = WAIT_START_ACK;
                    deadline = now + START_RETRY_MS;
                }
                break;
            case WAIT_START_ACK:
                {
                    int credits = HypseusActivity.nativeWatchCredits();
                    boolean creditSpent = creditsBeforeStart >= 0 && credits >= 0 &&
                        credits < creditsBeforeStart;
                    if (HypseusActivity.nativeWatchGameStarted() || creditSpent) {
                        phase = PLAYING;
                        HypseusActivity.nativeSetWatchAutomation(true);
                        HypseusActivity.nativeRequestCurrentWatchMove();
                    } else if (now >= deadline) {
                        phase = START_DOWN;
                        deadline = now;
                    }
                }
                break;
            case PLAYING:
                {
                    if (BuildConfig.DEBUG) {
                        long snapshot = HypseusActivity.nativeGuidance();
                        if (snapshot != tracedGuidance) {
                            tracedGuidance = snapshot;
                            Log.d("HypcadeWatch", "guidance=" + Long.toHexString(snapshot) + " time=" + now);
                        }
                    }
                    long event;
                    while ((event = HypseusActivity.nativeTakeWatchMove()) != 0) {
                        int controls = (int) event & 31;
                        if (controls != 0) { moves.clear(); moves.addLast(event); }
                    }
                    if (moveHeld && now >= deadline) releaseMove();
                    if (!moveHeld && !moves.isEmpty()) {
                        long queued = moves.removeFirst();
                        long current = HypseusActivity.nativeGuidance();
                        if ((current & 256) != 0 && (current >>> 32) == (queued >>> 32)
                                && (current & 31) == (queued & 31)) beginMove((int) queued & 31, now);
                    }
                }
                break;
            default:
                phase = WAIT_READY;
                break;
        }
        if (BuildConfig.DEBUG && phase != previousPhase)
            Log.d("HypcadeWatch", "phase=" + phase + " time=" + now);
        if (running) handler.postDelayed(tick, POLL_MS);
    }
}
