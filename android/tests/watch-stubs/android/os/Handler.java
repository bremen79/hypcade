/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package android.os;
import java.util.Comparator;
import java.util.PriorityQueue;
public final class Handler {
    private static final class Entry {
        final Handler owner;
        final Runnable action;
        final long when;
        final long order;
        Entry(Handler owner, Runnable action, long when, long order) {
            this.owner = owner; this.action = action; this.when = when; this.order = order;
        }
    }
    private static long serial;
    private static final PriorityQueue<Entry> QUEUE = new PriorityQueue<>(
            Comparator.comparingLong((Entry e) -> e.when).thenComparingLong(e -> e.order));
    public Handler(Looper looper) {}
    public boolean post(Runnable action) { return postDelayed(action, 0); }
    public boolean postDelayed(Runnable action, long delay) {
        QUEUE.add(new Entry(this, action, SystemClock.now + delay, serial++)); return true;
    }
    public void removeCallbacks(Runnable action) {
        QUEUE.removeIf(e -> e.owner == this && e.action == action);
    }
    public static void reset() { QUEUE.clear(); serial = 0; SystemClock.now = 0; }
    public static void advanceTo(long time) {
        if (time < SystemClock.now) throw new AssertionError("Clock moved backward");
        int iterations = 0;
        while (!QUEUE.isEmpty() && QUEUE.peek().when <= time) {
            if (++iterations > 100000) throw new AssertionError("Unbounded callback loop");
            Entry entry = QUEUE.remove(); SystemClock.now = entry.when; entry.action.run();
        }
        SystemClock.now = time;
    }
}
