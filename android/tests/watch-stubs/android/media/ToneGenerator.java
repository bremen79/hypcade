/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
// SPDX-License-Identifier: GPL-3.0-or-later
package android.media;
public final class ToneGenerator {
    public static final int TONE_PROP_BEEP = 24;
    public static int beeps;
    public ToneGenerator(int stream, int volume) {}
    public boolean startTone(int type, int duration) { beeps++; return true; }
    public void stopTone() {}
    public void release() {}
}
