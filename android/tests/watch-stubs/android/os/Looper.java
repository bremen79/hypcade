/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package android.os;
public final class Looper {
    private static final Looper MAIN = new Looper();
    private Looper() {}
    public static Looper getMainLooper() { return MAIN; }
}
