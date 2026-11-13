/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

import android.os.Handler;
import android.os.Looper;
import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.MotionEvent;

/** Standard controller buttons/sticks drive Android's existing focus navigation. */
final class ControllerNavigation {
    interface Dispatch { boolean send(KeyEvent event); }
    // Programmatically dispatched D-pad events do not pass through ViewRoot's
    // usual focus-navigation fallback. Reproduce it for stick/mapped inputs.
    static boolean dispatchFocus(android.view.View root, KeyEvent event, Dispatch base) {
        if (root.isInTouchMode() && event.getAction()==KeyEvent.ACTION_DOWN) {
            android.view.View focused=root.findFocus();
            // Public API exits touch mode, just like a physical D-pad event.
            (focused!=null ? focused : root).requestFocusFromTouch();
        }
        if (base.send(event)) return true;
        if (event.getAction() != KeyEvent.ACTION_DOWN || !(root instanceof android.view.ViewGroup)) return false;
        int direction;
        switch (event.getKeyCode()) {
            case KeyEvent.KEYCODE_DPAD_UP: direction=android.view.View.FOCUS_UP; break;
            case KeyEvent.KEYCODE_DPAD_DOWN: direction=android.view.View.FOCUS_DOWN; break;
            case KeyEvent.KEYCODE_DPAD_LEFT: direction=android.view.View.FOCUS_LEFT; break;
            case KeyEvent.KEYCODE_DPAD_RIGHT: direction=android.view.View.FOCUS_RIGHT; break;
            default: return false;
        }
        android.view.View next=android.view.FocusFinder.getInstance().findNextFocus(
                (android.view.ViewGroup)root,root.findFocus(),direction);
        if (next==null) return false;
        return next.requestFocus(direction);
    }
    private final Handler handler = new Handler(Looper.getMainLooper());
    private int held;
    private Dispatch target;
    private final Runnable repeat = new Runnable() {
        @Override public void run() {
            if (held == 0 || target == null) return;
            press(target, held);
            handler.postDelayed(this, 160);
        }
    };
    void reset() { handler.removeCallbacks(repeat); held = 0; target = null; }
    private static void press(Dispatch dispatch, int key) {
        dispatch.send(new KeyEvent(KeyEvent.ACTION_DOWN, key));
        dispatch.send(new KeyEvent(KeyEvent.ACTION_UP, key));
    }
    boolean key(KeyEvent event, Dispatch dispatch) {
        int mapped;
        switch (event.getKeyCode()) {
            case KeyEvent.KEYCODE_BUTTON_A:
            case KeyEvent.KEYCODE_BUTTON_1:
            case KeyEvent.KEYCODE_BUTTON_START:
            case KeyEvent.KEYCODE_CTRL_LEFT:
            case KeyEvent.KEYCODE_1:
            case KeyEvent.KEYCODE_2:
            case KeyEvent.KEYCODE_ENTER:
            case KeyEvent.KEYCODE_SPACE: mapped = KeyEvent.KEYCODE_DPAD_CENTER; break;
            case KeyEvent.KEYCODE_BUTTON_B:
            case KeyEvent.KEYCODE_BUTTON_2:
            case KeyEvent.KEYCODE_ALT_LEFT:
            case KeyEvent.KEYCODE_ESCAPE: mapped = KeyEvent.KEYCODE_BACK; break;
            default: return false;
        }
        reset();
        dispatch.send(new KeyEvent(event.getDownTime(), event.getEventTime(), event.getAction(),
                mapped, event.getRepeatCount(), event.getMetaState(), event.getDeviceId(),
                0, event.getFlags(), InputDevice.SOURCE_DPAD));
        return true;
    }
    void mapped(int key, boolean down, Dispatch dispatch) {
        if (key == KeyEvent.KEYCODE_5 || key == KeyEvent.KEYCODE_P) return;
        if (key == KeyEvent.KEYCODE_CTRL_LEFT || key == KeyEvent.KEYCODE_1 || key == KeyEvent.KEYCODE_2 || key == KeyEvent.KEYCODE_SPACE)
            key = KeyEvent.KEYCODE_DPAD_CENTER;
        else if (key == KeyEvent.KEYCODE_ALT_LEFT || key == KeyEvent.KEYCODE_ESCAPE) key = KeyEvent.KEYCODE_BACK;
        if (!down) { if (held == key) reset(); return; }
        reset();
        press(dispatch, key);
        if (key >= KeyEvent.KEYCODE_DPAD_UP && key <= KeyEvent.KEYCODE_DPAD_RIGHT) {
            held = key; target = dispatch; handler.postDelayed(repeat, 400);
        }
    }

    boolean motion(MotionEvent event, Dispatch dispatch) {
        if (!event.isFromSource(InputDevice.SOURCE_JOYSTICK)
                || event.getActionMasked() != MotionEvent.ACTION_MOVE) return false;
        float x = event.getAxisValue(MotionEvent.AXIS_HAT_X);
        float y = event.getAxisValue(MotionEvent.AXIS_HAT_Y);
        if (Math.abs(x) < .5f) x = event.getAxisValue(MotionEvent.AXIS_X);
        if (Math.abs(y) < .5f) y = event.getAxisValue(MotionEvent.AXIS_Y);
        int key = 0;
        if (Math.max(Math.abs(x), Math.abs(y)) > .55f) {
            key = Math.abs(y) >= Math.abs(x)
                    ? (y < 0 ? KeyEvent.KEYCODE_DPAD_UP : KeyEvent.KEYCODE_DPAD_DOWN)
                    : (x < 0 ? KeyEvent.KEYCODE_DPAD_LEFT : KeyEvent.KEYCODE_DPAD_RIGHT);
        }
        if (key != held) {
            reset();
            held = key;
            target = dispatch;
            if (key != 0) { press(dispatch, key); handler.postDelayed(repeat, 400); }
        }
        return true;
    }
}
