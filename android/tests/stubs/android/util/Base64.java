/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package android.util;

/** Host-test adapter only. Device builds use Android's API-8 Base64 implementation. */
public final class Base64 {
    public static final int NO_WRAP = 2;
    private Base64() {}
    public static String encodeToString(byte[] bytes, int flags) {
        if (flags != NO_WRAP) throw new AssertionError("Unsupported test flags");
        return java.util.Base64.getEncoder().encodeToString(bytes);
    }
    public static byte[] decode(String value, int flags) {
        if (flags != NO_WRAP) throw new AssertionError("Unsupported test flags");
        return java.util.Base64.getDecoder().decode(value);
    }
}
