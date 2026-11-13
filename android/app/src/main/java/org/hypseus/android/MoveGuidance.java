/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

import android.media.AudioManager;
import android.media.ToneGenerator;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

/** Audio on the same native ready event that makes the move text visible. */
final class MoveGuidance implements Runnable {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private ToneGenerator tone;
    private boolean running;
    private long lastSequence;

    MoveGuidance() {
        try { tone = new ToneGenerator(AudioManager.STREAM_MUSIC, 100); }
        catch (RuntimeException error) { Log.w("Hypseus", "Timing cue audio unavailable", error); }
    }
    void start() {
        if (running) return;
        running = true;
        lastSequence = HypseusActivity.nativeGuidance() >>> 32;
        handler.post(this);
    }
    void stop() {
        running = false;
        handler.removeCallbacks(this);
        if (tone != null) tone.stopTone();
    }
    void close() { stop(); if (tone != null) { tone.release(); tone = null; } }
    @Override public void run() {
        if (!running) return;
        long state = HypseusActivity.nativeGuidance();
        int controls = (int)state & 31;
        boolean ready = (state & 256) != 0;
        long sequence = state >>> 32;
        if (ready && sequence != lastSequence && controls != 0 && tone != null)
            tone.startTone(ToneGenerator.TONE_PROP_BEEP, 90);
        lastSequence = sequence;
        handler.postDelayed(this, 16);
    }
}
