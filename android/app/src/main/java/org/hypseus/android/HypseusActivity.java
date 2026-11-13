/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

import android.app.Activity;
import android.app.ActivityManager;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.Process;
import android.util.Log;
import android.view.View;
import android.view.WindowManager;

import org.libsdl.app.SDLActivity;

/** SDL host. The manifest isolates this activity in the private :emulator process. */
public final class HypseusActivity extends SDLActivity {
    static final String EXTRA_ARGUMENTS = "arguments";
    static final String EXTRA_CONTROLS = "controls";
    static final String EXTRA_TOUCH = "touch_controls";
    static final String EXTRA_SMOKE = "smoke_test";
    static final String EXTRA_WATCH = "watch_mode";
    static final String EXTRA_START_SKILL = "start_skill";
    static final String EXTRA_EXIT_CODE = "exit_code";
    private final Handler handler = new Handler(Looper.getMainLooper());
    private GameOverlay controls;
    private boolean exiting;
    private boolean watchMode;
    private WatchModeController watchController;
    private MoveGuidance guidance;
    private ArcadeInput arcadeInput;
    private android.hardware.input.InputManager inputManager;
    private final android.hardware.input.InputManager.InputDeviceListener deviceListener = new android.hardware.input.InputManager.InputDeviceListener() {
        @Override public void onInputDeviceAdded(int id) { }
        @Override public void onInputDeviceChanged(int id) { releaseMapped(); }
        @Override public void onInputDeviceRemoved(int id) { releaseMapped(); }
    };
    private void mappedKey(int code, boolean down) {
        if (mBrokenLibraries || exiting) return;
        if (code == android.view.KeyEvent.KEYCODE_ESCAPE) { if (down) requestExit(); return; }
        for (int action=0;action<ControlMap.KEYS.length;action++) if (ControlMap.KEYS[action]==code) {
            if (watchMode && action != 9) return;
            if (watchMode && action == 9 && down && watchController != null)
                watchController.toggleUserPause();
            nativeArcadeInput(action, down); break;
        }
    }
    private void releaseMapped() {
        if (arcadeInput != null) arcadeInput.release(this::mappedKey);
    }
    @Override public boolean dispatchKeyEvent(android.view.KeyEvent event) {
        if (arcadeInput != null && !mBrokenLibraries && arcadeInput.key(event, this::mappedKey)) return true;
        if (watchMode) {
            int code=event.getKeyCode();
            if (code==android.view.KeyEvent.KEYCODE_ESCAPE) {
                if (event.getAction()==android.view.KeyEvent.ACTION_DOWN) requestExit();
                return true;
            }
            if (code!=android.view.KeyEvent.KEYCODE_BACK && code!=android.view.KeyEvent.KEYCODE_VOLUME_UP
                    && code!=android.view.KeyEvent.KEYCODE_VOLUME_DOWN
                    && code!=android.view.KeyEvent.KEYCODE_VOLUME_MUTE) return true;
        }
        return super.dispatchKeyEvent(event);
    }
    @Override public boolean dispatchGenericMotionEvent(android.view.MotionEvent event) {
        if (arcadeInput != null && !mBrokenLibraries && arcadeInput.motion(event, this::mappedKey)) return true;
        if (watchMode) return true;
        return super.dispatchGenericMotionEvent(event);
    }

    public static native void nativeQuit();
    public static native void nativeConfigureDisplay(boolean mobile);
    public static native void nativeConfigureVideo(boolean enabled);
    public static native void nativeArcadeInput(int action, boolean down);
    public static native void nativeConfigureStartSkill(int skill);
    public static native void nativeEnableGuidance(int mode, boolean cue, boolean watch);
    public static native int nativeWatchCredits();
    public static native boolean nativeWatchCoinPending();
    public static native boolean nativeWatchGameStarted();
    public static native long nativeGuidance();
    public static native long nativeTakeWatchMove();
    public static native void nativeSetWatchAutomation(boolean active);
    public static native void nativeRequestCurrentWatchMove();
    public static native boolean nativeEmulatorReady();

    @Override protected String[] getLibraries() {
        return new String[]{"SDL3", "main"};
    }

    private boolean useTimingCue() {
        String[] arguments = getIntent().getStringArrayExtra(EXTRA_ARGUMENTS);
        return GuidanceSupport.forArguments(arguments).cue
                && getIntent().getBooleanExtra("timing_cue", false);
    }

    @Override protected String[] getArguments() {
        nativeConfigureDisplay(!BuildConfig.ARCADE);
        nativeConfigureVideo(true);
        nativeConfigureStartSkill(getIntent().getIntExtra(EXTRA_START_SKILL, 0));
        nativeEnableGuidance(GuidanceSupport.forArguments(
                getIntent().getStringArrayExtra(EXTRA_ARGUMENTS)).visual
                ? MoveMode.selected(getIntent().getIntExtra("move_mode", MoveMode.OFF)) : MoveMode.OFF, useTimingCue(),
                getIntent().getBooleanExtra(EXTRA_WATCH, false));
        String[] arguments = getIntent().getStringArrayExtra(EXTRA_ARGUMENTS);
        if (arguments == null) return new String[]{"--android-smoke-test"};
        if (!BuildConfig.ARCADE) return arguments;
        android.graphics.Point size = new android.graphics.Point();
        getWindowManager().getDefaultDisplay().getRealSize(size);
        return ArcadeDisplay.arguments(arguments, size.x, size.y);
    }

    @Override protected void main() {
        // Retain SDL's outer thread setup/teardown while reporting the native exit status.
        boolean configured = getIntent().getBooleanExtra(EXTRA_WATCH, false)
                || ControlMap.decode(getIntent().getStringExtra(EXTRA_CONTROLS))
                .canPlay(BuildConfig.ARCADE, getIntent().getBooleanExtra(EXTRA_TOUCH, true));
        int result = (configured || getIntent().getBooleanExtra(EXTRA_SMOKE, false))
                ? SDLActivity.nativeRunMain(getMainSharedObject(), getMainFunction(), getArguments()) : 1;
        Intent completion = new Intent();
        completion.putExtra(EXTRA_EXIT_CODE, result);
        completion.putExtra(EXTRA_SMOKE, getIntent().getBooleanExtra(EXTRA_SMOKE, false));
        setResult(Activity.RESULT_OK, completion);
    }

    @Override public void setRequestedOrientation(int orientation) {
        super.setRequestedOrientation(BuildConfig.ARCADE
                ? android.content.pm.ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE : orientation);
    }

    @Override protected void onCreate(Bundle savedInstanceState) {
        watchMode = getIntent().getBooleanExtra(EXTRA_WATCH, false);
        super.onCreate(savedInstanceState);
        if (mBrokenLibraries) return;
        arcadeInput = new ArcadeInput(ControlMap.decode(getIntent().getStringExtra(EXTRA_CONTROLS)));
        inputManager = (android.hardware.input.InputManager)getSystemService(INPUT_SERVICE);
        if (inputManager != null) inputManager.registerInputDeviceListener(deviceListener, handler);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        if (!BuildConfig.ARCADE) {
            controls = new GameOverlay(this, getIntent().getBooleanExtra(EXTRA_TOUCH, true),
                watchMode,
                new GameOverlay.Input() {
                    @Override public void key(int code, boolean pressed) {
                        if (mBrokenLibraries || exiting) return;
                        mappedKey(code, pressed);
                    }

                    @Override public void exit() {
                        requestExit();
                    }
                });
        }
        if (watchMode) {
            watchController = new WatchModeController();
            watchController.start();
        }
        // Visual moves are drawn natively; only optional timing audio needs polling.
        if (useTimingCue()) guidance = new MoveGuidance();
        immersive();
    }

    private void immersive() {
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
    }

    @Override protected void onResume() {
        super.onResume();
        if (!mBrokenLibraries) immersive();
        if (guidance != null) guidance.start();
        if (watchController != null) watchController.setLifecyclePaused(false);
    }

    @Override protected void onPause() {
        releaseMapped();
        if (controls != null) controls.releaseAll();
        if (guidance != null) guidance.stop();
        if (watchController != null) watchController.setLifecyclePaused(true);
        super.onPause();
    }

    @Override public void onWindowFocusChanged(boolean hasFocus) {
        if (!hasFocus) releaseMapped();
        if (!hasFocus && controls != null) controls.releaseAll();
        if (guidance != null) { if (hasFocus) guidance.start(); else guidance.stop(); }
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus && !mBrokenLibraries) immersive();
    }

    @Override public void onBackPressed() {
        requestExit();
    }

    private void requestExit() {
        if (exiting) return;
        releaseMapped();
        if (controls != null) controls.releaseAll();
        exiting = true;
        if (guidance != null) guidance.stop();
        if (watchController != null) watchController.stop();
        if (!mBrokenLibraries) nativeQuit();
        // Normal SDL main completion finishes the activity. Bound a stalled initialization too.
        handler.postDelayed(() -> {
            if (!isFinishing()) finish();
        }, 750);
    }

    @Override protected void onDestroy() {
        releaseMapped();
        if (inputManager != null) inputManager.unregisterInputDeviceListener(deviceListener);
        if (guidance != null) guidance.close();
        if (watchController != null) watchController.close();
        handler.removeCallbacksAndMessages(null);
        if (controls != null) controls.releaseAll();
        // SDL sends quit, joins the native main thread for up to one second, then releases its state.
        super.onDestroy();
        // Hypseus has process-wide desktop globals. End only this private process after cleanup.
        if (isEmulatorProcess()) Process.killProcess(Process.myPid());
        else Log.e("Hypseus", "Refusing to terminate a process other than :emulator");
    }

    private boolean isEmulatorProcess() {
        if (Build.VERSION.SDK_INT >= 28) {
            return (getPackageName() + ":emulator").equals(android.app.Application.getProcessName());
        }
        ActivityManager manager = (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);
        if (manager != null && manager.getRunningAppProcesses() != null) {
            for (ActivityManager.RunningAppProcessInfo process : manager.getRunningAppProcesses()) {
                if (process.pid == Process.myPid()) {
                    return (getPackageName() + ":emulator").equals(process.processName);
                }
            }
        }
        return false;
    }
}
