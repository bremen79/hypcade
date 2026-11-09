/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.view.inputmethod.InputMethodManager;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

/** Small platform-only launcher. There is no WebView, account, or network dependency. */
public final class LauncherActivity extends Activity implements GameData.Listener {
    private static final int STORAGE_ACCESS = 40;
    private static final int RUN_EMULATOR = 41;
    private static final int BACKGROUND = 0xff160f0d;
    private static final int CARD = 0xff261915;
    private static final int TEXT = 0xfffff3d6;
    private static final int MUTED = 0xffc8b394;
    private static final int ACCENT = 0xfff4c542;
    private static final String[] GAME_IDS = LaunchConfig.GAME_IDS;

    private final List<LaunchConfig> profiles = new ArrayList<>();
    private final List<LaunchConfig> library = new ArrayList<>();
    private TextView scanStatus;
    private LinearLayout manualSection;
    private SetupSettings setup;
    private LinearLayout setupSection, gameArea;
    private TextView inputStatus;
    private Button setupButton, controllerButton, resetController, debugButton;
    private TextView controllerStatus;
    private boolean setupWasComplete;
    private Button playButton;
    private boolean scanning;
    private String scannedRoot = "";
    private int scanGeneration;
    private java.util.concurrent.Future<?> scanTask;
    private final java.util.concurrent.ExecutorService scanner = java.util.concurrent.Executors.newSingleThreadExecutor();
    private ArcadeInput arcadeInput;
    private android.hardware.input.InputManager inputManager;
    private final android.hardware.input.InputManager.InputDeviceListener deviceListener = new android.hardware.input.InputManager.InputDeviceListener() {
        @Override public void onInputDeviceAdded(int id) { }
        @Override public void onInputDeviceChanged(int id) { releaseMenuControls(); }
        @Override public void onInputDeviceRemoved(int id) { releaseMenuControls(); }
    };
    private void releaseMenuControls() {
        if(arcadeInput!=null) arcadeInput.release(this::mappedMenuKey);
        navigation.reset();
    }
    private boolean routingControls;
    private ControllerNavigation.Dispatch mappingDestination;
    private void reloadControls() {
        releaseMenuControls();
        arcadeInput = new ArcadeInput(setup.controls());
    }
    private boolean dispatchMenuKey(android.view.KeyEvent event) {
        return ControllerNavigation.dispatchFocus(getWindow().getDecorView(),event,key->super.dispatchKeyEvent(key));
    }
    private void mappedMenuKey(int code, boolean down) {
        ControllerNavigation.Dispatch destination = mappingDestination;
        if (destination != null) navigation.mapped(code, down, event -> {
            routingControls = true;
            try { return destination.send(event); } finally { routingControls = false; }
        });
    }
    private final List<View> inputs = new ArrayList<>();
    private SharedPreferences preferences;
    private GameData.Work work;
    private ScrollView scroll;
    private LinearLayout content;
    private Button profilePicker;
    private TextView profileName;
    private Button gameId;
    private TextView detectedGame;
    private Button framefile;
    private Button script;
    private String extras = "";
    private Switch fastBoot;
    private Switch showScore;
    private Switch showFps;
    private boolean applyingOptions;
    private Switch linearScale;
    private Switch scanlines;
    private Switch syncVideo;
    private Switch hardwareVideo;
    private LinearLayout videoSection;
    private Switch moveHints;
    private Switch timingCue;
    private TextView assistanceStatus;
    private final ControllerNavigation navigation = new ControllerNavigation();
    private LinearLayout scriptSection;
    private LinearLayout advancedSection;
    private Switch touch;
    private TextView status;
    private TextView dataPath;
    private ProgressBar progress;
    private Button retry;
    private Button storageButton;
    private String currentId = "";
    private boolean resumed;
    private boolean emulatorOpen;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        if (BuildConfig.ARCADE) {
            setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE);
            getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
        }
        preferences = getSharedPreferences("games", MODE_PRIVATE);
        setup = new SetupSettings(this);
        loadProfiles();
        reloadControls();
        inputManager=(android.hardware.input.InputManager)getSystemService(INPUT_SERVICE);
        if(inputManager!=null) inputManager.registerInputDeviceListener(deviceListener,null);
        buildInterface();
        LaunchConfig draft = null;
        try {
            String saved = state == null ? preferences.getString("draft", "") : state.getString("draft", "");
            if (!saved.isEmpty()) draft = fromJson(new JSONObject(saved));
        } catch (JSONException ignored) {
            // A damaged draft does not remove saved profiles or game data.
        }
        if (draft == null) draft = profiles.isEmpty() ? emptyProfile() : profiles.get(0);
        applyProfile(draft);
        refreshProfiles();

        Object retained = getLastNonConfigurationInstance();
        work = retained instanceof GameData.Work ? (GameData.Work) retained : new GameData.Work(this);
        work.attach(this);
        if (retained == null) work.prepare();
        storageButton.requestFocus();
    }

    private void buildInterface() {
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(BACKGROUND);
        scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setClipToPadding(false);
        content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(18), dp(20), dp(18), dp(28));
        FrameLayout.LayoutParams contents = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.TOP | Gravity.CENTER_HORIZONTAL);
        scroll.addView(content, contents);
        root.addView(scroll, new FrameLayout.LayoutParams(-1, -1));
        setContentView(root);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            int left, top, right, bottom;
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets safe = insets.getInsets(
                        WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout() | WindowInsets.Type.ime());
                left = safe.left; top = safe.top; right = safe.right; bottom = safe.bottom;
            } else {
                left = insets.getSystemWindowInsetLeft(); top = insets.getSystemWindowInsetTop();
                right = insets.getSystemWindowInsetRight(); bottom = insets.getSystemWindowInsetBottom();
            }
            view.setPadding(left, top, right, bottom);
            return insets;
        });
        root.requestApplyInsets();
        root.addOnLayoutChangeListener((view, l, t, r, b, ol, ot, or, ob) -> {
            int available = view.getWidth() - view.getPaddingLeft() - view.getPaddingRight();
            int width = BuildConfig.ARCADE ? available : Math.min(dp(680), available);
            if (width > 0 && content.getLayoutParams().width != width) {
                content.getLayoutParams().width = width;
                content.requestLayout();
            }
        });

        TextView eyebrow = text("LASERDISC ARCADE", 11, ACCENT);
        eyebrow.setLetterSpacing(.16f);
        content.addView(eyebrow);
        TextView title = text("Hypcade", 32, TEXT);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        content.addView(title, spaced(-1, -2, 4));
        content.addView(text(BuildConfig.ARCADE ? "Version for Android arcades" : "Secondary mobile version", 13, MUTED), spaced(-1, -2, 2));

        LinearLayout statusCard = card();
        status = text("Preparing emulator resources…", 14, MUTED);
        status.setTextIsSelectable(false);
        statusCard.addView(status);
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setIndeterminate(true);
        progress.setIndeterminateTintList(ColorStateList.valueOf(ACCENT));
        statusCard.addView(progress, spaced(-1, dp(4), 12));
        retry = action("Retry setup", false, view -> work.prepare());
        retry.setVisibility(View.GONE);
        statusCard.addView(retry, spaced(-1, dp(44), 8));

        setupButton = action("Directory & controller", false, view -> toggleSection(setupSection));
        content.addView(setupButton, spaced(-1, dp(48), 12));
        setupSection = new LinearLayout(this);
        setupSection.setOrientation(LinearLayout.VERTICAL);
        content.addView(setupSection);
        LinearLayout storage = card(setupSection);
        heading(storage, "1   GAME DATA");
        storage.addView(text("Choose the folder containing roms/, vldp/ and/or singe/.", 14, MUTED));
        storageButton = action("Choose game folder / SD card", false, view -> chooseStorage());
        storage.addView(storageButton, spaced(-1, dp(48), 12));
        dataPath = text("Checking available storage…", 11, MUTED);
        dataPath.setTextIsSelectable(false);
        storage.addView(dataPath, spaced(-1, -2, 10));

        LinearLayout controller = card(setupSection);
        heading(controller, BuildConfig.ARCADE ? "2   CONTROLLER FOR ALL GAMES" : "CONTROLS FOR ALL GAMES");
        controllerStatus = text("Configure and save your controller to continue.", 14, MUTED);
        controller.addView(controllerStatus);
        controllerButton = action(BuildConfig.ARCADE ? "Configure controller" : "Configure controller (optional)", false, view -> {
            releaseMenuControls();
            new ControlWizard(this, () -> { reloadControls(); onDataChanged(work); }).show();
        });
        controller.addView(controllerButton, spaced(-1, dp(48), 8));
        resetController = action("Reset controller", false, view -> dialogBuilder()
                .setTitle("Reset controller?").setMessage(BuildConfig.ARCADE
                        ? "You will need to configure the controller again before playing any game."
                        : "The saved controller mapping will be removed. Enable on-screen controls to play without a controller.")
                .setNegativeButton("Cancel", null).setPositiveButton("Reset", (dialog, which) -> {
                    if (!setup.clearControls()) { showError("Could not save controller settings."); return; }
                    reloadControls(); onDataChanged(work); revealSection(setupSection);
                }).show());
        controller.addView(resetController, spaced(-1, dp(44), 4));
        if (!BuildConfig.ARCADE) {
            touch = new Switch(this);
            touch.setText("On-screen controls (all games)");
            styleSwitch(touch);
            touch.setChecked(setup.touchControls());
            touch.setOnCheckedChangeListener((button, checked) -> {
                if (checked != setup.touchControls() && !setup.saveTouchControls(checked)) {
                    button.setChecked(setup.touchControls()); showError("Could not save on-screen controls setting.");
                }
                onDataChanged(work);
            });
            controller.addView(touch, spaced(-1, dp(50), 8));
        }
        gameArea = new LinearLayout(this);
        gameArea.setOrientation(LinearLayout.VERTICAL);
        gameArea.setVisibility(View.GONE);
        content.addView(gameArea);
        LinearLayout game = card(gameArea);
        heading(game, "AVAILABLE GAMES");
        game.addView(text("Joystick / D-pad: move · A / Start: select · B: back", 12, MUTED));
        profilePicker = input(action("Choose game", false, view -> chooseAvailableGame()));
        profilePicker.setContentDescription("Available games");
        game.addView(profilePicker, spaced(-1, dp(48), 0));
        scanStatus = text("Choose a game folder to find available games.", 12, MUTED);
        game.addView(scanStatus, spaced(-1, -2, 6));
        game.addView(input(action("Rescan games", false, view -> scanGames(true))), spaced(-1, dp(44), 6));
        manualSection = new LinearLayout(this);
        manualSection.setOrientation(LinearLayout.VERTICAL);
        profileName = text("", 14, MUTED);
        manualSection.addView(profileName, spaced(-1, -2, 12));
        framefile = fileField(manualSection, "Framefile", "Choose framefile", false);
        detectedGame = text("Choose a framefile to detect the game.", 14, MUTED);
        manualSection.addView(detectedGame, spaced(-1, -2, 6));
        gameId = input(action("", false, view -> chooseGame()));
        gameId.setHint("Choose game / ROM version");
        scriptSection = new LinearLayout(this);
        scriptSection.setOrientation(LinearLayout.VERTICAL);
        script = fileField(scriptSection, "Singe script or ZIP", "Choose script or ZIP", true);
        manualSection.addView(scriptSection);
        game.addView(input(action("Video & performance", false, view -> {
            toggleSection(videoSection);
        })), spaced(-1, dp(44), 14));
        videoSection = new LinearLayout(this);
        videoSection.setOrientation(LinearLayout.VERTICAL);
        showFps = option(videoSection, "Show FPS");
        hardwareVideo = option(videoSection, "Hardware MPEG-2 decoding (automatic fallback)");
        scanlines = option(videoSection, "CRT scanlines (GPU)");
        linearScale = option(videoSection, "Smooth video scaling");
        syncVideo = option(videoSection, "V-sync");
        videoSection.addView(text("Scanlines and smoothing add rendering work. Turning off V-sync can reduce display waits but may make presentation less smooth.", 12, MUTED), spaced(-1, -2, 6));
        videoSection.setVisibility(View.GONE);
        game.addView(videoSection);

        Button advanced = input(action("Game Options", false, view -> {
            toggleSection(advancedSection);
        }));
        game.addView(advanced, spaced(-1, dp(44), 14));
        advancedSection = new LinearLayout(this);
        advancedSection.setOrientation(LinearLayout.VERTICAL);
        advancedSection.addView(manualSection);
        label(advancedSection, "Game / ROM override (only if detection is incorrect)");
        advancedSection.addView(gameId, spaced(-1, dp(48), 4));
        fastBoot = option(advancedSection, "Fast startup");
        showScore = option(advancedSection, "Show score and lives");
        moveHints = option(advancedSection, "Show correct moves");
        timingCue = option(advancedSection, "Play move timing cue");
        assistanceStatus = text("", 12, MUTED);
        advancedSection.addView(assistanceStatus, spaced(-1, -2, 8));
        advancedSection.setVisibility(View.GONE);
        game.addView(advancedSection);

        playButton = input(action("Start game", true, view -> startGame()));
        gameArea.addView(playButton, spaced(-1, dp(56), 18));
        LinearLayout tools = row();
        debugButton = input(action("Debug", false, view -> showDebugMenu()));
        addEqual(tools, debugButton);
        addEqual(tools, action("Exit", false, view -> {
            saveDraft();
            releaseMenuControls();
            finishAndRemoveTask();
        }));
        content.addView(tools, spaced(-1, dp(48), 10));
        inputStatus = text("", 12, MUTED);
        gameArea.addView(inputStatus, spaced(-1, -2, 16));
        content.addView(action("About", false, view -> showAbout()), spaced(-1, dp(48), 10));
        TextView footer = text("Hypcade " + BuildConfig.VERSION_NAME + " · Based on Hypseus Singe 3.0.2\n"
                + "GPL-3.0-or-later · No warranty · Redistribution permitted under the GPL.\n"
                + "Credits and AI assistance: About.", 11, MUTED);
        content.addView(footer, spaced(-1, -2, 20));

    }

    private LaunchConfig emptyProfile() {
        return new LaunchConfig("", "", "", "", "", "-fastboot");
    }

    private LaunchConfig readProfile() {
        return new LaunchConfig(currentId, profileName.getText().length() == 0 ? profileTitle() : profileName.getText().toString(), gameId.getText().toString(),
                framefile.getText().toString(), script.getText().toString(), selectedOptions(),
                moveHints.isChecked(), timingCue.isChecked(), showScore.isChecked());
    }

    private void applyProfile(LaunchConfig config) {
        applyingOptions = true;
        currentId = config.id;
        profileName.setText(config.name);
        gameId.setText(config.game);
        framefile.setText(config.framefile);
        script.setText(config.script);
        extras = config.extraArguments;
        List<String> options = safeOptions();
        VideoOptions video = new VideoOptions(options);
        fastBoot.setChecked(video.fastBoot);
        showFps.setChecked(video.showFps);
        showScore.setChecked(config.showScore);
        linearScale.setChecked(video.smooth);
        scanlines.setChecked(video.scanlines);
        syncVideo.setChecked(video.vsync);
        hardwareVideo.setChecked(video.hardware);
        moveHints.setChecked(config.showMoves);
        timingCue.setChecked(config.timingCue);
        updateGameOptions();
        advancedSection.setVisibility(View.GONE);
        videoSection.setVisibility(View.GONE);
        applyingOptions = false;
    }

    private void refreshProfiles() {
        String label = scanning ? "Scanning games…" : "No playable games found";
        for (LaunchConfig game : library) if (game.id.equals(currentId)) label=game.name;
        profilePicker.setText(label);
        profilePicker.setEnabled(setupComplete() && !work.busy && !scanning && !library.isEmpty() && !emulatorOpen);
    }

    private void chooseAvailableGame() {
        if (scanning || library.isEmpty()) return;
        String[] names = new String[library.size()];
        for (int i=0;i<library.size();i++) names[i]=library.get(i).name;
        dialogBuilder().setTitle("Choose game").setItems(names,(dialog,which)->{
            rememberCurrent();
            applyProfile(library.get(which));
            refreshProfiles();
        }).setNegativeButton("Cancel",null).show();
    }

    private void rememberCurrent() {
        if(currentId.isEmpty()) return;
        LaunchConfig config=readProfile();
        for(int i=0;i<profiles.size();i++) if(profiles.get(i).id.equals(config.id)) {profiles.set(i,config);config=null;break;}
        if(config!=null) profiles.add(config);
        for(int i=0;i<library.size();i++) if(library.get(i).id.equals(currentId)) library.set(i,readProfile());
        persistProfiles();
    }

    private void scanGames(boolean force) {
        if(!setupComplete() || work.busy || emulatorOpen) return;
        final String path=work.home.getAbsolutePath();
        if(!force && path.equals(scannedRoot)) return;
        rememberCurrent();
        scannedRoot=path; scanning=true;
        final int generation=++scanGeneration;
        if(scanTask!=null) scanTask.cancel(true);
        library.clear(); refreshProfiles();
        scanStatus.setText("Scanning game framefiles…");
        playButton.setEnabled(false);
        final File home=work.home;
        final List<LaunchConfig> saved=new ArrayList<>(profiles);
        final java.lang.ref.WeakReference<LauncherActivity> owner=new java.lang.ref.WeakReference<>(this);
        final android.os.Handler main=new android.os.Handler(android.os.Looper.getMainLooper());
        scanTask=scanner.submit(()->{
            GameScanner.Result result;
            String error=null;
            try { result=GameScanner.scan(home,saved,()->Thread.currentThread().isInterrupted()); }
            catch(IOException failure) { result=new GameScanner.Result();error=failure.getMessage(); }
            final GameScanner.Result found=result;
            final String failure=error;
            if(Thread.currentThread().isInterrupted()) return;
            main.post(()->{
                LauncherActivity activity=owner.get();
                if(activity==null || activity.isDestroyed() || generation!=activity.scanGeneration || !activity.setupComplete()) return;
                activity.scanning=false;
                activity.library.addAll(found.games);
                // Snapshot every first discovery, including games not selected yet.
                for (LaunchConfig game : found.games) {
                    boolean known = false;
                    for (LaunchConfig savedGame : activity.profiles)
                        if (savedGame.id.equals(game.id)) { known = true; break; }
                    if (!known) activity.profiles.add(game);
                }
                activity.persistProfiles();
                LaunchConfig selected=null;
                for(LaunchConfig game:found.games) if(game.id.equals(activity.currentId)) selected=game;
                if(selected==null && !found.games.isEmpty()) selected=found.games.get(0);
                activity.applyProfile(selected==null ? activity.emptyProfile() : selected);
                activity.refreshProfiles();
                activity.scanStatus.setText(failure!=null ? failure : found.games.size()+" games available"
                    +(found.commandErrors.isEmpty() ? "" : " · Commands: " + android.text.TextUtils.join("; ", found.commandErrors))
                    +(found.limited ? " · Scan limit reached; choose a smaller folder." : "")
                    +(found.skipped>0 ? " · "+found.skipped+" unrecognized, incomplete or unreadable entries skipped. Game Options allow manual setup." : ""));
                activity.playButton.setEnabled(activity.setupComplete() && activity.setup.canPlay() && !activity.work.busy && !found.games.isEmpty() && !activity.emulatorOpen);
            });
        });
    }

    private void saveManualSelection() {
        LaunchConfig config = readProfile();
        if (config.game.isEmpty() || config.framefile.isEmpty() ||
                (config.game.equals("singe") && config.script.isEmpty())) {
            saveDraft();
            return;
        }
        try {
            config.validateSettings();
            if (config.id.isEmpty()) config = config.withId(UUID.randomUUID().toString());
            int index = -1;
            for (int i = 0; i < profiles.size(); i++) if (profiles.get(i).id.equals(config.id)) index = i;
            if (index < 0) profiles.add(config); else profiles.set(index, config);
            currentId = config.id;
            persistProfiles();
            saveDraft();
            refreshProfiles();
            scanGames(true);

        } catch (IllegalArgumentException error) {
            showError(error.getMessage());
        }
    }

    private void loadProfiles() {
        try {
            JSONArray array = new JSONArray(preferences.getString("profiles", "[]"));
            for (int i = 0; i < array.length(); i++) {
                JSONObject item = array.optJSONObject(i);
                if (item != null) {
                    LaunchConfig profile = fromJson(item);
                    if (!profile.id.isEmpty()) profiles.add(profile);
                }
            }
        } catch (JSONException ignored) {
            Toast.makeText(this, "Saved profiles could not be read. Game files are still available.", Toast.LENGTH_LONG).show();
        }
    }

    private void persistProfiles() {
        JSONArray array = new JSONArray();
        for (LaunchConfig profile : profiles) array.put(toJson(profile));
        preferences.edit().putString("profiles", array.toString()).apply();
    }

    private void saveDraft() {
        if (preferences != null && profileName != null) {
            preferences.edit().putString("draft", toJson(readProfile()).toString()).apply();
        }
    }

    private static JSONObject toJson(LaunchConfig config) {
        JSONObject json = new JSONObject();
        try {
            json.put("score", config.showScore);
            json.put("id", config.id).put("name", config.name).put("game", config.game)
                    .put("framefile", config.framefile).put("script", config.script)
                    .put("extra", config.extraArguments).put("moves", config.showMoves).put("cue", config.timingCue);
        } catch (JSONException impossible) {
            throw new IllegalStateException(impossible);
        }
        return json;
    }

    private static LaunchConfig fromJson(JSONObject json) {
        return new LaunchConfig(json.optString("id", ""), json.optString("name", ""), json.optString("game", "lair"),
                json.optString("framefile", ""), json.optString("script", ""), json.optString("extra", ""),
                json.optBoolean("moves", false), json.optBoolean("cue", false), json.optBoolean("score", true));
    }

    private void chooseStorage() {
        if (work.busy || emulatorOpen) return;
        saveDraft();
        hideKeyboard();
        requestFolderAccess();
    }

    private void requestFolderAccess() {
        if (Build.VERSION.SDK_INT >= 30) {
            if (Environment.isExternalStorageManager()) {
                showStorageRoots();
                return;
            }
            dialogBuilder().setTitle("Allow direct folder access")
                    .setMessage("To access your game folder, enable Allow access "
                            + "to manage all files for Hypcade on the next screen. Android grants shared-storage "
                            + "access; Hypcade uses the game folder you select.")
                    .setNegativeButton("Cancel", null)
                    .setPositiveButton("Open settings", (dialog, which) -> {
                        try {
                            startActivityForResult(new Intent(android.provider.Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                                    Uri.parse("package:" + getPackageName())), STORAGE_ACCESS);
                        } catch (ActivityNotFoundException error) {
                            showError("This Android installation has no all-files access settings. Shared game folders cannot be selected.");
                        }
                    }).show();
        } else if (checkSelfPermission(android.Manifest.permission.READ_EXTERNAL_STORAGE)
                != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{android.Manifest.permission.READ_EXTERNAL_STORAGE}, STORAGE_ACCESS);
        } else {
            showStorageRoots();
        }
    }

    @Override public void onRequestPermissionsResult(int request, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(request, permissions, results);
        if (request == STORAGE_ACCESS) {
            if (checkSelfPermission(android.Manifest.permission.READ_EXTERNAL_STORAGE)
                    == android.content.pm.PackageManager.PERMISSION_GRANTED) showStorageRoots();
            else showError("Storage access was not granted. Allow storage access to choose a game folder.");
        }
    }

    private void showStorageRoots() {
        List<File> roots = new ArrayList<>();
        List<String> labels = new ArrayList<>();
        for (File directory : GameData.storageDirectories(this)) {
            if (directory == null || !GameData.readableStorage(directory)) continue;
            File root = directory;
            // getExternalFilesDirs has the documented /Android/data/<package>/files layout.
            for (int i = 0; i < 4 && root != null; ++i) root = root.getParentFile();
            if (root == null || roots.contains(root)) continue;
            roots.add(root);
            labels.add((Environment.isExternalStorageRemovable(directory) ? "SD card" : "Internal shared storage")
                    + "\n" + root.getPath());
        }
        if (roots.isEmpty()) {
            showError("No mounted storage found. Reinsert the card and try again.");
            return;
        }
        dialogBuilder().setTitle("Choose storage to browse")
                .setItems(labels.toArray(new String[0]), (dialog, which) -> browseFolder(roots.get(which), roots.get(which)))
                .setNegativeButton("Cancel", null).show();
    }

    private void browseFolder(File root, File folder) {
        try {
            File current = folder.getCanonicalFile();
            LaunchConfig.requireInside(root.getCanonicalFile(), current);
            File[] children = current.listFiles(file -> file.isDirectory() && !file.getName().startsWith("."));
            if (children == null) throw new IOException("Android prevents access to this folder. Choose another folder.");
            Arrays.sort(children, Comparator.comparing(File::getName, String.CASE_INSENSITIVE_ORDER));
            List<File> entries = new ArrayList<>();
            List<String> labels = new ArrayList<>();
            if (!current.equals(root.getCanonicalFile())) {
                entries.add(current.getParentFile());
                labels.add("↑  Parent folder");
            }
            for (File child : children) {
                entries.add(child);
                labels.add("›  " + child.getName() + "/");
            }
            dialogBuilder().setTitle(current.getPath())
                    .setItems(labels.toArray(new String[0]), (dialog, which) -> browseFolder(root, entries.get(which)))
                    .setNegativeButton("Cancel", null)
                    .setNeutralButton("Storage", (dialog, which) -> chooseStorage())
                    .setPositiveButton("Use this folder", (dialog, which) -> {
                        try {
                            work.selectFolder(current);
                            scroll.smoothScrollTo(0, 0);
                        } catch (IOException error) {
                            showError(error.getMessage());
                        }
                    }).show();
        } catch (IOException | SecurityException error) {
            showError(error.getMessage());
        }
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == STORAGE_ACCESS && Build.VERSION.SDK_INT >= 30) {
            if (Environment.isExternalStorageManager()) showStorageRoots();
            else showError("All files access is disabled. Enable it to choose a game folder.");
        } else if (requestCode == RUN_EMULATOR) {
            emulatorOpen = false;
            if (resultCode == RESULT_OK && data != null && data.hasExtra(HypseusActivity.EXTRA_EXIT_CODE)) {
                int code = data.getIntExtra(HypseusActivity.EXTRA_EXIT_CODE, -1);
                boolean test = data.getBooleanExtra(HypseusActivity.EXTRA_SMOKE, false);
                if (test && code == 0) {
                    work.status = "Display test passed. Rendering and audio-device initialization completed. The test is silent.";
                    work.failed = false;
                } else if (test) {
                    work.status = "Display test failed (code " + code + "). Check the Android log for HYPSEUS_ANDROID_SMOKE.";
                    work.failed = true;
                } else {
                    work.status = "Returned to launcher (native exit " + code + "). "
                            + "If the game did not start, open Debug → View last log.";
                    work.failed = code != 0;
                }
            } else {
                work.status = "Returned to launcher. If the game stopped unexpectedly, open Debug → View last log.";
                work.failed = false;
            }
            onDataChanged(work);
            scroll.smoothScrollTo(0, 0);
        }
    }

    private void startGame() {
        if (!setupComplete() || !setup.canPlay() || work.busy || emulatorOpen) return;
        rememberCurrent();
        saveDraft();
        hideKeyboard();
        work.validate(readProfile());
        scroll.smoothScrollTo(0, 0);
    }

    private void showAbout() {
        dialogBuilder().setTitle("About Hypcade " + BuildConfig.VERSION_NAME)
                .setMessage("Hypcade " + BuildConfig.VERSION_NAME + "\n\n"
                        + "An independent Android arcade-focused fork and adaptation of Hypseus Singe 3.0.2. "
                        + "Includes modified engine code and an Android launcher.\n\n"
                        + "Hypseus Singe © 2021–2026 DirtBagXon\n"
                        + "Hypseus © 2016 Jeffrey Clark\n"
                        + "Daphne © 1999–2013 Matt Ownby\n"
                        + "Singe originally by Scott Duensing; additional contributors and component notices are included.\n\n"
                        + "Hypcade modifications: 2026-11-08. AI-assisted development used GPT-6-Astra and Codex.\n\n"
                        + "GNU GPL version 3 or later. You may redistribute and modify this software under the GPL. "
                        + "NO WARRANTY, including merchantability or fitness for a particular purpose.\n\n"
                        + "License texts and third-party notices are in the source repository.")
                .setNegativeButton("Close", null).show();
    }

    private void showDebugMenu() {
        dialogBuilder().setTitle("Debug")
                .setItems(new String[]{"Display test", "View last log"}, (dialog, which) -> {
                    if (which == 0) showSmokeTest();
                    else showLog();
                })
                .setNegativeButton("Close", null).show();
    }

    private void showSmokeTest() {
        dialogBuilder().setTitle("Display test")
                .setMessage("A colour pattern should appear for about two seconds. "
                        + "The test also opens the audio device silently. No game files are needed.")
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Run test", (dialog, which) -> launch(new String[]{"--android-smoke-test"}, true)).show();
    }

    private void launch(String[] arguments, boolean smoke) {
        launch(arguments, smoke, false, false);
    }

    private void launch(String[] arguments, boolean smoke, boolean moves, boolean cue) {
        if (emulatorOpen || (!smoke && (!setupComplete() || !setup.canPlay()))) return;
        saveDraft();
        hideKeyboard();
        Intent intent = new Intent(this, HypseusActivity.class);
        intent.putExtra(HypseusActivity.EXTRA_ARGUMENTS, arguments);
        intent.putExtra(HypseusActivity.EXTRA_CONTROLS, setup.encodedControls());
        GuidanceSupport support = GuidanceSupport.forArguments(arguments);
        intent.putExtra("move_hints", moves && support.visual);
        intent.putExtra("timing_cue", cue && support.cue);
        intent.putExtra(HypseusActivity.EXTRA_TOUCH, !BuildConfig.ARCADE && setup.touchControls());
        intent.putExtra(HypseusActivity.EXTRA_SMOKE, smoke);
        emulatorOpen = true;
        for (View input : inputs) input.setEnabled(false);
        startActivityForResult(intent, RUN_EMULATOR);
    }

    @Override public void onDataChanged(GameData.Work changed) {
        if (isFinishing() || isDestroyed()) return;
        if(scanning && (!setupComplete() || !changed.ready || changed.busy || changed.home==null || !changed.home.getAbsolutePath().equals(scannedRoot))) {
            ++scanGeneration;
            if(scanTask!=null) scanTask.cancel(true);
            scanning=false;scannedRoot="";library.clear();refreshProfiles();
        }
        status.setText(changed.status);
        status.setTextColor(changed.failed ? 0xffffb1a8 : MUTED);
        progress.setVisibility(changed.busy ? View.VISIBLE : View.GONE);
        retry.setVisibility(!changed.busy && !changed.ready ? View.VISIBLE : View.GONE);
        storageButton.setEnabled(!changed.busy && !emulatorOpen);
        boolean complete = setupComplete();
        boolean available = !changed.busy && !emulatorOpen;
        if (complete != setupWasComplete) {
            setupSection.setVisibility(complete ? View.GONE : View.VISIBLE);
            if (complete) revealSection(gameArea);
            setupWasComplete = complete;
        }
        if (!complete) setupSection.setVisibility(View.VISIBLE);
        setupButton.setVisibility(complete ? View.VISIBLE : View.GONE);
        setupButton.setEnabled(available);
        gameArea.setVisibility(complete ? View.VISIBLE : View.GONE);
        debugButton.setVisibility(complete ? View.VISIBLE : View.GONE);
        controllerButton.setEnabled(changed.ready && changed.home != null && available);
        resetController.setEnabled(!setup.encodedControls().isEmpty() && available);
        controllerStatus.setText(setup.controls().isComplete() ? "Configured for all games"
                : BuildConfig.ARCADE ? "Configure and save your controller to continue."
                : "Controller optional. Use on-screen controls to play without one.");
        inputStatus.setText(setup.canPlay()
                ? "Choose a game and press Start game. Game settings are saved automatically."
                : "Enable on-screen controls or configure a controller in Directory & controller to play.");
        if (touch != null) touch.setEnabled(available);
        for (View input : inputs) input.setEnabled(complete && available);
        updateGameOptions();
        if (complete && available) scanGames(false);
        profilePicker.setEnabled(complete && !changed.busy && !scanning && !library.isEmpty() && !emulatorOpen);
        playButton.setEnabled(complete && setup.canPlay() && !changed.busy && !scanning && !currentId.isEmpty() && !emulatorOpen);
        dataPath.setText("Game folder\n" + (changed.home != null ? changed.home.getPath()
                : setup.directory().isEmpty() ? "No storage selected" : setup.directory()));
        if (resumed && !changed.busy) {
            GameData.LaunchRequest request = changed.takeLaunch();
            if (request != null) launch(request.arguments, false,
                    request.config.showMoves, request.config.timingCue);
        }
    }

    private void browse(Button field, boolean scripts) {
        if (work.home == null) return;
        hideKeyboard();
        File root = work.home;
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(16), dp(8), dp(16), 0);
        TextView location = text("/", 13, ACCENT);
        panel.addView(location);
        CheckBox allFiles = new CheckBox(this);
        allFiles.setText("Show all files");
        allFiles.setTextColor(MUTED);
        panel.addView(allFiles);
        ListView list = new ListView(this);
        panel.addView(list, new LinearLayout.LayoutParams(-1, dp(320)));
        AlertDialog dialog = dialogBuilder().setTitle(scripts ? "Choose Singe script / ZIP" : "Choose framefile")
                .setView(panel).setNegativeButton("Cancel", null).create();
        File[] directory = {root};
        List<File> entries = new ArrayList<>();
        Runnable refresh = () -> {
            try {
                String relative = LaunchConfig.relativePath(root, directory[0]);
                location.setText(relative.isEmpty() ? "/" : relative);
                entries.clear();
                List<String> labels = new ArrayList<>();
                if (!directory[0].equals(root)) {
                    entries.add(directory[0].getParentFile());
                    labels.add("↑  Parent folder");
                }
                File[] children = directory[0].listFiles(file -> {
                    if (file.getName().startsWith(".")) return false;
                    if (file.isDirectory() || allFiles.isChecked()) return true;
                    String name = file.getName().toLowerCase(Locale.ROOT);
                    return scripts ? name.endsWith(".singe") || name.endsWith(".lua") || name.endsWith(".zip")
                            : name.endsWith(".txt") || name.endsWith(".frame") || name.endsWith(".framefile");
                });
                if (children == null) throw new IOException("Cannot read this folder.");
                Arrays.sort(children, Comparator.comparing((File file) -> !file.isDirectory())
                        .thenComparing(File::getName, String.CASE_INSENSITIVE_ORDER));
                for (File child : children) {
                    entries.add(child);
                    labels.add(child.isDirectory() ? "›  " + child.getName() + "/" : child.getName());
                }
                list.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_list_item_1, labels));
            } catch (IOException error) {
                Toast.makeText(this, error.getMessage(), Toast.LENGTH_LONG).show();
            }
        };
        list.setOnItemClickListener((parent, view, position, id) -> {
            if (position >= entries.size()) return;
            File selected = entries.get(position);
            if (selected.isDirectory()) {
                directory[0] = selected;
                refresh.run();
            } else {
                try {
                    field.setText(LaunchConfig.relativePath(root, selected));
                    if (!scripts) {
                        gameId.setText(LaunchConfig.inferGame(framefile.getText().toString()));
                        updateGameOptions();
                    }
                    profileName.setText(profileTitle());
                    dialog.dismiss();
                    if (!scripts && gameId.getText().length() == 0) chooseGame();
                    else if (!gameId.getText().toString().equals("singe") || script.getText().length() > 0)
                        saveManualSelection();
                } catch (IOException error) {
                    Toast.makeText(this, error.getMessage(), Toast.LENGTH_LONG).show();
                }
            }
        });
        allFiles.setOnCheckedChangeListener((view, checked) -> refresh.run());
        dialog.show();
        refresh.run();
    }

    private void showLog() {
        File log = new File(work.stateHome, "logs/hypseus.log");
        new Thread(() -> {
            String output;
            try (RandomAccessFile file = new RandomAccessFile(log, "r")) {
                int length = (int) Math.min(file.length(), 128 * 1024);
                byte[] bytes = new byte[length];
                file.seek(file.length() - length);
                file.readFully(bytes);
                output = new String(bytes, StandardCharsets.UTF_8);
                if (output.isEmpty()) output = "The game log is empty.";
            } catch (IOException error) {
                output = "No game log yet. Start a game first. The display test writes its result to the Android log.";
            }
            String text = output;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                TextView logText = text(text, 11, TEXT);
                logText.setTypeface(Typeface.MONOSPACE);
                logText.setTextIsSelectable(false);
                logText.setPadding(dp(18), dp(12), dp(18), dp(12));
                ScrollView logScroll = new ScrollView(this);
                logScroll.addView(logText);
                dialogBuilder().setTitle("Last game log")
                        .setView(logScroll).setPositiveButton("Close", null).show();
            });
        }, "game-log").start();
    }

    private void showError(String message) {
        dialogBuilder().setTitle("Check game settings").setMessage(message)
                .setPositiveButton("OK", null).show();
    }

    private void hideKeyboard() {
        View focused = getCurrentFocus();
        if (focused != null) {
            InputMethodManager keyboard = (InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE);
            if (keyboard != null) keyboard.hideSoftInputFromWindow(focused.getWindowToken(), 0);
            focused.clearFocus();
        }
    }

    @Override protected void onResume() {
        super.onResume();
        resumed = true;
        if (work != null) onDataChanged(work);
    }

    @Override protected void onPause() {
        rememberCurrent();
        if(arcadeInput!=null) arcadeInput.release(this::mappedMenuKey);
        resumed = false;
        navigation.reset();
        saveDraft();
        super.onPause();
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        state.putString("draft", toJson(readProfile()).toString());
        super.onSaveInstanceState(state);
    }

    @Override public Object onRetainNonConfigurationInstance() {
        return work;
    }

    @Override protected void onDestroy() {
        ++scanGeneration;
        if(scanTask!=null) scanTask.cancel(true);
        scanner.shutdownNow();
        releaseMenuControls();
        if(inputManager!=null) inputManager.unregisterInputDeviceListener(deviceListener);
        if (work != null) {
            work.detach();
            if (!isChangingConfigurations()) work.close();
        }
        super.onDestroy();
    }

    private int dp(float value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private <T extends View> T input(T view) {
        view.setFocusable(true);
        inputs.add(view);
        return view;
    }

    private TextView text(String value, int size, int color) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(color);
        view.setLineSpacing(dp(2), 1f);
        return view;
    }

    private boolean setupComplete() {
        return work != null && work.ready && work.home != null && (!BuildConfig.ARCADE || setup.controls().isComplete());
    }

    private void toggleSection(View section) {
        boolean expand = section.getVisibility() != View.VISIBLE;
        section.setVisibility(expand ? View.VISIBLE : View.GONE);
        if (expand) revealSection(section);
    }

    private void revealSection(View section) {
        section.post(() -> {
            if (isDestroyed() || section.getVisibility() != View.VISIBLE) return;
            if (!section.isInTouchMode()) {
                ArrayList<View> focusable = new ArrayList<>();
                section.addFocusables(focusable, View.FOCUS_FORWARD);
                if (!focusable.isEmpty()) focusable.get(0).requestFocus();
            }
            android.graphics.Rect bounds = new android.graphics.Rect();
            section.getDrawingRect(bounds);
            content.offsetDescendantRectToMyCoords(section, bounds);
            scroll.smoothScrollTo(0, Math.max(0, bounds.top - dp(12)));
        });
    }

    private LinearLayout card() { return card(content); }

    private LinearLayout card(LinearLayout parent) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(16), dp(16), dp(16), dp(16));
        GradientDrawable fill = new GradientDrawable();
        fill.setColor(CARD);
        fill.setCornerRadius(dp(16));
        card.setBackground(fill);
        parent.addView(card, spaced(-1, -2, 18));
        return card;
    }

    private void heading(LinearLayout parent, String value) {
        TextView heading = text(value, 11, ACCENT);
        heading.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        heading.setLetterSpacing(.12f);
        LinearLayout.LayoutParams params = spaced(-1, -2, 0);
        params.bottomMargin = dp(12);
        parent.addView(heading, params);
    }

    private void label(LinearLayout parent, String value) {
        parent.addView(text(value, 13, MUTED), spaced(-1, -2, 14));
    }

    private Button fileField(LinearLayout parent, String name, String hint, boolean scripts) {
        label(parent, name);
        Button field = input(action("", false, null));
        field.setHint(hint);
        field.setHintTextColor(TEXT);
        field.setOnClickListener(view -> browse(field, scripts));
        parent.addView(field, spaced(-1, dp(60), 4));
        return field;
    }

    private Switch option(LinearLayout parent, String title) {
        Switch control = input(new Switch(this));
        control.setText(title);
        styleSwitch(control);
        control.setOnCheckedChangeListener((button, checked) -> {
            if (!applyingOptions && showScore != null && timingCue != null) {
                rememberCurrent();
                saveDraft();
            }
        });
        parent.addView(control, spaced(-1, dp(50), 4));
        return control;
    }

    private String profileTitle() {
        String path = framefile.getText().toString();
        String name = path.isEmpty() ? "New profile" : new File(path).getName();
        int dot = name.lastIndexOf('.');
        if (dot > 0) name = name.substring(0, dot);
        String title = gameId.getText().length() == 0 ? name : gameId.getText() + " · " + name;
        return title.length() > 100 ? title.substring(0, 100) : title;
    }

    private List<String> safeOptions() {
        try { return LaunchConfig.splitArguments(extras); }
        catch (IllegalArgumentException invalid) { return new ArrayList<>(); }
    }

    private String selectedOptions() {
        List<String> inherited = safeOptions();
        VideoOptions video = new VideoOptions(inherited);
        video.fastBoot = fastBoot.isChecked() && LaunchConfig.supportsFastBoot(gameId.getText().toString());
        video.showFps = showFps.isChecked();
        video.smooth = linearScale.isChecked();
        video.scanlines = scanlines.isChecked();
        video.vsync = syncVideo.isChecked();
        video.hardware = hardwareVideo.isChecked();
        return video.arguments(inherited);
    }

    private void chooseGame() {
        dialogBuilder().setTitle(gameId.getText().length() == 0
                        ? "Game not detected — choose ROM version" : "Override game / ROM version")
                .setItems(GAME_IDS, (dialog, which) -> {
                    gameId.setText(GAME_IDS[which]);
                    moveHints.setChecked(false);
                    updateGameOptions();
                    profileName.setText(profileTitle());
                    saveManualSelection();
                }).setNegativeButton("Cancel", null).show();
    }

    private void updateGameOptions() {
        String game = gameId.getText().toString();
        detectedGame.setText(game.isEmpty() ? "Choose a framefile to detect the game."
                : "Game: " + game);
        scriptSection.setVisibility(game.equals("singe") ? View.VISIBLE : View.GONE);
        GuidanceSupport support = GuidanceSupport.forGame(game, safeOptions());
        boolean available = setupComplete() && !work.busy && !emulatorOpen;
        showScore.setEnabled(available && LaunchConfig.supportsScore(game, safeOptions()));
        showScore.setText(LaunchConfig.supportsScore(game, safeOptions()) ? "Show score and lives" : game.equals("lair2") ? "Score and lives — requires DL2 US 3.19" : "Score and lives — game-controlled / unavailable");
        fastBoot.setEnabled(available && LaunchConfig.supportsFastBoot(game));
        fastBoot.setText(LaunchConfig.supportsFastBoot(game) ? "Fast startup" : "Fast startup — unavailable");
        moveHints.setEnabled(available && support.visual);
        timingCue.setEnabled(available && support.cue);
        if (!support.visual) moveHints.setChecked(false);
        if (!support.cue) timingCue.setChecked(false);
        moveHints.setText(support.visual ? "Show correct moves" : support.scriptControlled
                ? "Correct moves — use game menu" : "Correct moves — unavailable");
        timingCue.setText(support.cue ? "Play move timing cue" : support.scriptControlled
                ? "Timing cue — use game menu" : game.equals("lair2")
                ? "Timing cue — included in video" : "Timing cue — unavailable");
        assistanceStatus.setText(support.scriptControlled
                ? "Map Game options / Service in Controller setup, then press that button in the game to open its original menu (where supported). Hints and cues are controlled there."
                : !support.visual ? "No bundled hints for this game / ROM version."
                : game.equals("lair2") ? "Dragon's Lair II 3.19: visual hints use the game's original prompts; audio cues are supplied by the video; no extra cue is added."
                : "Experimental guidance for this ROM: only recognized safe move windows are shown. Unrecognized scenes stay silent.");
    }

    private AlertDialog.Builder dialogBuilder() {
        return new AlertDialog.Builder(this) {
            @Override public AlertDialog create() {
                AlertDialog dialog = super.create();
                ControllerNavigation controls = new ControllerNavigation();
                dialog.setOnDismissListener(ignored -> { controls.reset(); releaseMenuControls(); });
                dialog.setOnKeyListener((ignored, key, event) -> {
                    if (!routingControls && arcadeInput != null) {
                        mappingDestination=e -> ControllerNavigation.dispatchFocus(dialog.getWindow().getDecorView(),e,dialog::dispatchKeyEvent);
                        if (arcadeInput.key(event, LauncherActivity.this::mappedMenuKey)) return true;
                    }
                    return controls.key(event, e -> ControllerNavigation.dispatchFocus(dialog.getWindow().getDecorView(),e,dialog::dispatchKeyEvent));
                });
                dialog.setOnShowListener(ignored -> {
                    View decor = dialog.getWindow().getDecorView();
                    if (dialog.getListView() != null) {
                        GradientDrawable selected = new GradientDrawable();
                        selected.setColor(0xff8f2028);
                        selected.setStroke(dp(3), 0xfff4c542);
                        dialog.getListView().setSelector(selected);
                    }
                    decor.setOnGenericMotionListener((view, event) -> {
                        mappingDestination=e -> ControllerNavigation.dispatchFocus(dialog.getWindow().getDecorView(),e,dialog::dispatchKeyEvent);
                        if(arcadeInput!=null && arcadeInput.motion(event,LauncherActivity.this::mappedMenuKey)) return true;
                        return controls.motion(event,e -> ControllerNavigation.dispatchFocus(dialog.getWindow().getDecorView(),e,dialog::dispatchKeyEvent));
                    });
                    decor.getViewTreeObserver().addOnWindowFocusChangeListener(focused -> { if (!focused) controls.reset(); });
                });
                return dialog;
            }
        };
    }

    @Override public void onWindowFocusChanged(boolean focused) {
        super.onWindowFocusChanged(focused);
        if (!focused) {
            if(arcadeInput!=null) arcadeInput.release(this::mappedMenuKey);
            navigation.reset();
        }
    }

    @Override public boolean dispatchKeyEvent(android.view.KeyEvent event) {
        if (!routingControls && arcadeInput != null) {
            mappingDestination=this::dispatchMenuKey;
            if(arcadeInput.key(event,this::mappedMenuKey)) return true;
        }
        return navigation.key(event, this::dispatchMenuKey) || super.dispatchKeyEvent(event);
    }

    @Override public boolean dispatchGenericMotionEvent(android.view.MotionEvent event) {
        mappingDestination=this::dispatchMenuKey;
        if(arcadeInput!=null && arcadeInput.motion(event,this::mappedMenuKey)) return true;
        return navigation.motion(event, this::dispatchMenuKey) || super.dispatchGenericMotionEvent(event);
    }

    private android.graphics.drawable.Drawable focusBackground(int normal) {
        android.graphics.drawable.StateListDrawable states = new android.graphics.drawable.StateListDrawable();
        int[][] conditions = {new int[]{-android.R.attr.state_enabled},
                new int[]{android.R.attr.state_focused}, new int[]{android.R.attr.state_pressed}, new int[]{}};
        for (int i = 0; i < conditions.length; i++) {
            GradientDrawable fill = new GradientDrawable();
            fill.setCornerRadius(dp(8));
            fill.setColor(i == 0 ? 0xff302622 : i == 1 || i == 2 ? 0xff8f2028 : normal);
            if (i == 1 || i == 2) fill.setStroke(dp(3), 0xfff4c542);
            states.addState(conditions[i], fill);
        }
        return states;
    }

    private void styleSwitch(Switch view) {
        view.setTextSize(14);
        view.setTextColor(new ColorStateList(new int[][]{new int[]{-android.R.attr.state_enabled}, new int[]{android.R.attr.state_focused}, new int[]{}},
                new int[]{0xff777777, 0xffffffff, TEXT}));
        view.setBackground(focusBackground(0x00000000));
        view.setPadding(dp(12), 0, dp(12), 0);
        view.setShowText(false);
        int[][] states = {new int[]{-android.R.attr.state_enabled}, new int[]{android.R.attr.state_checked}, new int[]{}};
        view.setThumbTintList(new ColorStateList(states, new int[]{0xff777777, ACCENT, 0xffb49a79}));
        view.setTrackTintList(new ColorStateList(states, new int[]{0xff444444, 0xff8f2028, 0xff594335}));
    }

    private Button action(String title, boolean primary, View.OnClickListener click) {
        Button button = new Button(this);
        button.setText(title);
        button.setAllCaps(false);
        button.setTextSize(primary ? 17 : 13);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setTextColor(new ColorStateList(new int[][]{new int[]{-android.R.attr.state_enabled}, new int[]{android.R.attr.state_focused}, new int[]{}},
                new int[]{0xff8e7e70, 0xffffffff, primary ? BACKGROUND : TEXT}));
        button.setBackgroundTintList(null);
        button.setBackground(focusBackground(primary ? ACCENT : 0xff402820));
        button.setPadding(dp(8), 0, dp(8), 0);
        button.setMinWidth(0);
        button.setMinimumWidth(0);
        button.setOnClickListener(click);
        return button;
    }

    private LinearLayout row() {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        return row;
    }

    private void addEqual(LinearLayout row, View view) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -1, 1);
        if (row.getChildCount() > 0) params.leftMargin = dp(6);
        row.addView(view, params);
    }

    private LinearLayout.LayoutParams spaced(int width, int height, int top) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(width, height);
        params.topMargin = dp(top);
        return params;
    }
}
