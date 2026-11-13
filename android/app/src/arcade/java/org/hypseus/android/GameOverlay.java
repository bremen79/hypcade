/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;
/** Compile-time arcade replacement: no Views, input overlay or enable path. */
final class GameOverlay {
    interface Input { void key(int code, boolean down); void exit(); }
    GameOverlay(android.app.Activity activity, boolean visible, boolean watchMode, Input input) { }
    void releaseAll() { }
}
