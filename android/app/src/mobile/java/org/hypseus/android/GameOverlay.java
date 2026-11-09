/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;
import android.app.Activity;
import android.os.Build;
import android.view.ViewGroup;
import android.view.WindowInsets;
final class GameOverlay {
    interface Input { void key(int code, boolean down); void exit(); }
    private final TouchControls controls;
    GameOverlay(Activity activity, boolean visible, Input input) {
        String[] arguments = activity.getIntent().getStringArrayExtra(HypseusActivity.EXTRA_ARGUMENTS);
        boolean singe = arguments != null && arguments.length > 0 && "singe".equals(arguments[0]);
        controls = new TouchControls(activity, visible, singe, new TouchControls.Input() {
            @Override public void key(int code, boolean down) { input.key(code, down); }
            @Override public void exit() { input.exit(); }
        });
        activity.addContentView(controls, new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        controls.setOnApplyWindowInsetsListener((view, insets) -> {
            int left = 0, top = 0, right = 0, bottom = 0;
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets safe = insets.getInsets(WindowInsets.Type.displayCutout());
                left = safe.left; top = safe.top; right = safe.right; bottom = safe.bottom;
            } else if (Build.VERSION.SDK_INT >= 28 && insets.getDisplayCutout() != null) {
                left = insets.getDisplayCutout().getSafeInsetLeft();
                top = insets.getDisplayCutout().getSafeInsetTop();
                right = insets.getDisplayCutout().getSafeInsetRight();
                bottom = insets.getDisplayCutout().getSafeInsetBottom();
            }
            view.setPadding(left, top, right, bottom);
            return insets;
        });
        controls.requestApplyInsets();
    }
    void releaseAll() { controls.releaseAll(); }
}
