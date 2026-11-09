/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.util.SparseIntArray;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Small native Android overlay. Empty areas let touches reach SDL's surface. */
final class TouchControls extends FrameLayout {
    interface Input {
        void key(int androidKeyCode, boolean pressed);
        void exit();
    }

    private final Input input;
    private final List<KeyButton> keyButtons = new ArrayList<>();
    private final DirectionPad pad;
    private final FrameLayout actions;
    private final LinearLayout utility;
    private final Button toggle;
    private final KeyButton gameOptions;
    private boolean controlsVisible;

    TouchControls(Context context, boolean visible, boolean singe, Input input) {
        super(context);
        this.input = input;
        setMotionEventSplittingEnabled(true);
        setFocusable(false);

        Button exit = button("Exit");
        exit.setContentDescription("Exit game and return to launcher");
        exit.setOnClickListener(view -> input.exit());
        addView(exit, position(64, 44, Gravity.TOP | Gravity.START, 12, 10, 0, 0));

        toggle = button("Hide touch");
        toggle.setOnClickListener(view -> showControls(!controlsVisible));
        addView(toggle, position(92, 44, Gravity.TOP | Gravity.END, 0, 10, 12, 0));

        utility = new LinearLayout(context);
        utility.setGravity(Gravity.CENTER);
        utility.setMotionEventSplittingEnabled(true);
        for (KeyButton key : new KeyButton[]{
                keyButton("Coin", "Insert coin", KeyEvent.KEYCODE_5),
                keyButton("Start", "Start player one", KeyEvent.KEYCODE_1),
                keyButton("Start 2", "Start two players", KeyEvent.KEYCODE_2),
                keyButton("Pause", "Pause or resume", KeyEvent.KEYCODE_P)}) {
            LinearLayout.LayoutParams item = new LinearLayout.LayoutParams(dp(58), dp(44));
            item.setMargins(dp(2), 0, dp(2), 0);
            utility.addView(key, item);
        }
        addView(utility, position(248, 44, Gravity.TOP | Gravity.CENTER_HORIZONTAL, 0, 10, 0, 0));

        gameOptions = singe ? keyButton("Options", "Open the game’s original options menu",
                KeyEvent.KEYCODE_9) : null;
        if (gameOptions != null)
            addView(gameOptions, position(76, 44, Gravity.TOP | Gravity.START, 12, 62, 0, 0));

        pad = new DirectionPad(context);
        addView(pad, position(164, 164, Gravity.BOTTOM | Gravity.START, 14, 0, 0, 14));

        actions = new FrameLayout(context);
        actions.setMotionEventSplittingEnabled(true);
        actions.addView(keyButton("A", "Action one", KeyEvent.KEYCODE_CTRL_LEFT),
                position(66, 66, Gravity.BOTTOM | Gravity.END, 0, 0, 0, 0));
        actions.addView(keyButton("B", "Action two", KeyEvent.KEYCODE_ALT_LEFT),
                position(58, 58, Gravity.BOTTOM | Gravity.START, 0, 0, 0, 18));
        actions.addView(keyButton("C", "Action three", KeyEvent.KEYCODE_SPACE),
                position(54, 54, Gravity.TOP | Gravity.CENTER_HORIZONTAL, 0, 0, 0, 0));
        addView(actions, position(144, 142, Gravity.BOTTOM | Gravity.END, 0, 0, 20, 20));
        showControls(visible);
    }

    private LayoutParams position(int width, int height, int gravity,
                                  int left, int top, int right, int bottom) {
        LayoutParams params = new LayoutParams(dp(width), dp(height), gravity);
        params.setMargins(dp(left), dp(top), dp(right), dp(bottom));
        return params;
    }

    private int dp(float value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private Button button(String label) {
        Button button = new Button(getContext());
        styleButton(button, label);
        return button;
    }

    private void styleButton(Button button, String label) {
        button.setText(label);
        button.setAllCaps(false);
        button.setTextSize(label.length() == 1 ? 22 : 12);
        button.setTextColor(Color.WHITE);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setPadding(0, 0, 0, 0);
        button.setMinWidth(0);
        button.setMinimumWidth(0);
        button.setMinHeight(0);
        button.setMinimumHeight(0);
        button.setFocusable(false);
        button.setStateListAnimator(null);
        StateListDrawable states = new StateListDrawable();
        states.addState(new int[]{android.R.attr.state_pressed}, background(0xcc8f2028, 0xfff4c542));
        states.addState(new int[]{}, background(0x88160f0d, 0x88ffffff));
        button.setBackground(states);
        button.setBackgroundTintList((ColorStateList) null);
    }

    private GradientDrawable background(int fill, int stroke) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(fill);
        drawable.setCornerRadius(dp(14));
        drawable.setStroke(dp(1), stroke);
        return drawable;
    }

    private KeyButton keyButton(String label, String description, int keyCode) {
        KeyButton button = new KeyButton(getContext(), keyCode);
        styleButton(button, label);
        button.setContentDescription(description);
        keyButtons.add(button);
        return button;
    }

    void showControls(boolean visible) {
        releaseAll();
        controlsVisible = visible;
        int visibility = visible ? VISIBLE : GONE;
        pad.setVisibility(visibility);
        actions.setVisibility(visibility);
        utility.setVisibility(visibility);
        if (gameOptions != null) gameOptions.setVisibility(visibility);
        toggle.setText(visible ? "Hide touch" : "Show touch");
    }

    void releaseAll() {
        for (KeyButton button : keyButtons) button.release();
        if (pad != null) pad.release();
    }

    private final class KeyButton extends Button {
        private final int code;
        private final Set<Integer> tracked = new HashSet<>();
        private boolean down;
        private boolean touchClick;
        private final Runnable pulseRelease = () -> update(false);

        KeyButton(Context context, int code) {
            super(context);
            this.code = code;
        }

        private void update(boolean pressed) {
            if (down != pressed) {
                down = pressed;
                input.key(code, pressed);
            }
            setPressed(pressed);
        }

        void release() {
            removeCallbacks(pulseRelease);
            tracked.clear();
            update(false);
        }

        @Override public boolean onTouchEvent(MotionEvent event) {
            int action = event.getActionMasked();
            int index = event.getActionIndex();
            if (action == MotionEvent.ACTION_DOWN || action == MotionEvent.ACTION_POINTER_DOWN) {
                removeCallbacks(pulseRelease);
                tracked.add(event.getPointerId(index));
                getParent().requestDisallowInterceptTouchEvent(true);
            } else if (action == MotionEvent.ACTION_CANCEL) {
                release();
                return true;
            } else if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_POINTER_UP) {
                tracked.remove(event.getPointerId(index));
            }
            boolean pressed = false;
            for (int i = 0; i < event.getPointerCount(); i++) {
                if (tracked.contains(event.getPointerId(i)) && event.getX(i) >= 0
                        && event.getX(i) < getWidth() && event.getY(i) >= 0
                        && event.getY(i) < getHeight()) pressed = true;
            }
            update(pressed);
            if (action == MotionEvent.ACTION_UP) {
                touchClick = true;
                performClick();
                touchClick = false;
            }
            return true;
        }

        @Override public boolean performClick() {
            super.performClick();
            if (!touchClick) {
                // Accessibility-generated clicks still produce a useful short key press.
                update(true);
                removeCallbacks(pulseRelease);
                postDelayed(pulseRelease, 100);
            }
            return true;
        }
    }

    /** A sliding, diagonal-capable D-pad; key state is the union of all held pointers. */
    private final class DirectionPad extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final SparseIntArray pointers = new SparseIntArray();
        private final int[] codes = {KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT,
                KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN};
        private int held;

        DirectionPad(Context context) {
            super(context);
            setContentDescription("Directional pad; slide for diagonal movement");
            setFocusable(false);
        }

        private int mask(float x, float y) {
            if (x < 0 || y < 0 || x >= getWidth() || y >= getHeight()) return 0;
            float dx = (x - getWidth() / 2f) / (getWidth() / 2f);
            float dy = (y - getHeight() / 2f) / (getHeight() / 2f);
            int result = 0;
            if (dx < -.25f) result |= 1;
            if (dx > .25f) result |= 2;
            if (dy < -.25f) result |= 4;
            if (dy > .25f) result |= 8;
            return result;
        }

        private void update() {
            int next = 0;
            for (int i = 0; i < pointers.size(); i++) next |= pointers.valueAt(i);
            for (int i = 0; i < codes.length; i++) {
                int bit = 1 << i;
                if ((next & bit) != (held & bit)) input.key(codes[i], (next & bit) != 0);
            }
            held = next;
            invalidate();
        }

        void release() {
            pointers.clear();
            update();
        }

        @Override public boolean onTouchEvent(MotionEvent event) {
            int action = event.getActionMasked();
            int index = event.getActionIndex();
            if (action == MotionEvent.ACTION_DOWN || action == MotionEvent.ACTION_POINTER_DOWN) {
                pointers.put(event.getPointerId(index), mask(event.getX(index), event.getY(index)));
                getParent().requestDisallowInterceptTouchEvent(true);
            } else if (action == MotionEvent.ACTION_MOVE) {
                for (int i = 0; i < event.getPointerCount(); i++) {
                    int id = event.getPointerId(i);
                    if (pointers.indexOfKey(id) >= 0) pointers.put(id, mask(event.getX(i), event.getY(i)));
                }
            } else if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_POINTER_UP) {
                pointers.delete(event.getPointerId(index));
                if (action == MotionEvent.ACTION_UP) performClick();
            } else if (action == MotionEvent.ACTION_CANCEL) {
                pointers.clear();
            }
            update();
            return true;
        }

        @Override public boolean performClick() {
            return super.performClick();
        }

        @Override protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            float w = getWidth(), h = getHeight();
            paint.setColor(0x88160f0d);
            canvas.drawRoundRect(w * .34f, 0, w * .66f, h, dp(14), dp(14), paint);
            canvas.drawRoundRect(0, h * .34f, w, h * .66f, dp(14), dp(14), paint);
            String[] labels = {"‹", "›", "⌃", "⌄"};
            float[] xs = {w * .16f, w * .84f, w * .5f, w * .5f};
            float[] ys = {h * .5f, h * .5f, h * .16f, h * .84f};
            paint.setTextAlign(Paint.Align.CENTER);
            paint.setTypeface(Typeface.DEFAULT_BOLD);
            paint.setTextSize(dp(30));
            for (int i = 0; i < 4; i++) {
                if ((held & (1 << i)) != 0) {
                    paint.setColor(0xcc8f2028);
                    canvas.drawCircle(xs[i], ys[i], w * .15f, paint);
                }
                paint.setColor(Color.WHITE);
                canvas.drawText(labels[i], xs[i], ys[i] - (paint.ascent() + paint.descent()) / 2f, paint);
            }
            paint.setColor(0x99f4c542);
            canvas.drawCircle(w / 2, h / 2, dp(7), paint);
        }
    }
}
