/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package android.os;
public final class SystemClock {
    private SystemClock() {}
    static long now;
    public static long uptimeMillis() { return now; }
}
