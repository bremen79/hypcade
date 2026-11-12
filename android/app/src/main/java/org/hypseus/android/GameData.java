/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

import android.content.Context;
import android.content.res.AssetManager;
import android.os.Handler;
import android.os.Looper;
import android.os.Environment;
import android.system.ErrnoException;
import android.system.Os;
import android.system.OsConstants;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Prepares private support resources separately from the read-only game folder. */
final class GameData {
    private GameData() {}

    static File[] storageDirectories(Context context) {
        return context.getExternalFilesDirs(null);
    }

    static boolean readableStorage(File directory) {
        String state = Environment.getExternalStorageState(directory);
        return Environment.MEDIA_MOUNTED.equals(state) || Environment.MEDIA_MOUNTED_READ_ONLY.equals(state);
    }

    interface Listener {
        void onDataChanged(Work work);
    }

    static final class LaunchRequest {
        final LaunchConfig config;
        final String[] arguments;
        final boolean watchMode;

        LaunchRequest(LaunchConfig config, String[] arguments, boolean watchMode) {
            this.config = config;
            this.arguments = arguments;
            this.watchMode = watchMode;
        }
    }

    /** Retained across Activity recreation; it never keeps an Activity or a View. */
    static final class Work {
        private final Context context;
        private final Handler main = new Handler(Looper.getMainLooper());
        private final ExecutorService executor = Executors.newSingleThreadExecutor();
        private Listener listener;
        private LaunchRequest launch;
        private volatile boolean closed;

        volatile File home;
        volatile File stateHome;
        volatile boolean ready;
        volatile boolean busy;
        volatile boolean failed;
        volatile String status = "Preparing emulator resources…";

        Work(Context context) {
            this.context = context.getApplicationContext();
        }

        synchronized void attach(Listener listener) {
            this.listener = listener;
            publish();
        }

        synchronized void detach() {
            listener = null;
        }

        synchronized LaunchRequest takeLaunch() {
            LaunchRequest result = launch;
            launch = null;
            return result;
        }

        void prepare() {
            execute("Preparing emulator resources…", () -> {
                ready = false;
                String selected = new SetupSettings(context).directory();
                home = selected.isEmpty() ? null : new File(selected).getCanonicalFile();
                if (home != null) checkDirectFolder(home);
                stateHome = new File(context.getFilesDir(), "hypseus").getCanonicalFile();
                makeDirectory(stateHome);
                File staging = stagingDirectory(stateHome);
                makeDirectory(staging);
                File[] abandoned = staging.listFiles();
                if (abandoned != null) {
                    for (File part : abandoned) {
                        if (part.isFile() && part.getName().matches("[0-9a-f-]{36}\\.part")) {
                            deleteIfExists(part);
                        }
                    }
                }
                for (String name : new String[]{"ram", "logs", "screenshots", "indexes"}) {
                    makeDirectory(checkedChild(stateHome, name));
                }
                AssetManager assets = context.getAssets();
                String[] roots = assets.list("hypseus");
                if (roots == null || roots.length == 0) {
                    throw new IOException("The installation is missing emulator resources. Reinstall the APK.");
                }
                // Only writable input defaults need filesystem paths. Graphics, sounds
                // and fonts are read directly from APK assets by SDL.
                for (String name : new String[]{"hypinput.ini", "hypinput_gamepad.ini"}) {
                    prepareInputConfig(assets, name);
                }
                File noMedia = new File(stateHome, ".nomedia");
                if (!noMedia.exists() && !noMedia.createNewFile()) {
                    throw new IOException("Could not prepare game storage.");
                }
                trimIndexes(new File(stateHome, "indexes"));
                ready = true;
                return home == null ? "Choose a game folder to get started."
                        : "Ready";
            });
        }

        void selectFolder(File folder) throws IOException {
            if (busy) return;
            File selected = folder.getCanonicalFile();
            checkDirectFolder(selected);
            if (!new SetupSettings(context).saveDirectory(selected.getPath())) {
                throw new IOException("Could not save the game directory. Free some internal storage and retry.");
            }
            ready = false;
            home = null;
            prepare();
        }

        private static void checkDirectFolder(File folder) throws IOException {
            if (!readableStorage(folder) || !folder.isDirectory() || folder.list() == null) {
                throw new IOException("Cannot read this folder. Check storage permission and that the card is mounted. No files were copied.");
            }
        }

        private static void trimIndexes(File directory) {
            File[] files = directory.listFiles(File::isFile);
            if (files == null) return;
            java.util.Arrays.sort(files, java.util.Comparator.comparingLong(File::lastModified));
            long size = 0;
            for (File file : files) size += file.length();
            for (File file : files) {
                if (size <= 8L * 1024 * 1024) break;
                long length = file.length();
                if (file.delete()) size -= length;
            }
        }

        private void requireMountedStorage() throws IOException {
            if (home == null || !readableStorage(home) || !home.isDirectory()) {
                ready = false;
                throw new IOException("Game storage was removed. Reinsert the selected card and retry setup.");
            }
        }

        void validate(LaunchConfig config, boolean watchMode) {
            if (!ready) return;
            execute("Checking game files…", () -> {
                requireMountedStorage();
                if (!watchMode && !new SetupSettings(context).canPlay()) {
                    throw new IOException(BuildConfig.ARCADE ? "Configure and save a controller before starting a game."
                            : "Enable on-screen controls or configure a controller before starting a game.");
                }
                trimIndexes(new File(stateHome, "indexes"));
                String[] arguments = config.arguments(home, stateHome);
                synchronized (this) {
                    launch = new LaunchRequest(config, arguments, watchMode);
                }
                return "Starting " + (config.name.isEmpty() ? config.game : config.name) + "…";
            });
        }

        void close() {
            closed = true;
            detach();
            executor.shutdown();
        }

        private interface Task {
            String run() throws Exception;
        }

        private synchronized void execute(String initial, Task task) {
            if (busy || closed) return;
            busy = true;
            failed = false;
            status = initial;
            publish();
            executor.execute(() -> {
                try {
                    String completion = task.run();
                    checkCancelled();
                    status = completion;
                } catch (Cancelled error) {
                    status = "Setup cancelled. No game files were copied.";
                } catch (Exception error) {
                    failed = true;
                    String detail = error.getMessage();
                    status = detail == null ? "Could not prepare the selected folder." : detail;
                } finally {
                    busy = false;
                    publish();
                }
            });
        }

        private void publish() {
            main.post(() -> {
                Listener current;
                synchronized (Work.this) {
                    current = listener;
                }
                if (current != null) current.onDataChanged(Work.this);
            });
        }

        private void checkCancelled() throws Cancelled {
            if (closed) throw new Cancelled();
        }

        private void prepareInputConfig(AssetManager assets, String name) throws IOException {
            checkCancelled();
            File destination = checkedChild(stateHome, name);
            if (!destination.exists()) {
                try (InputStream stream = assets.open("hypseus/" + name)) {
                    copyStream(stream, destination);
                }
            } else if (!destination.isFile()) {
                throw new IOException("An input configuration file has been replaced by a folder: " + name);
            }
        }

        private File checkedChild(File directory, String name) throws IOException {
            if (name == null || name.isEmpty() || name.equals(".") || name.equals("..")
                    || name.indexOf('/') >= 0 || name.indexOf('\\') >= 0 || name.indexOf('\0') >= 0) {
                throw new IOException("Invalid resource filename.");
            }
            File result = new File(directory, name).getCanonicalFile();
            LaunchConfig.requireInside(stateHome, result);
            if (result.equals(new File(stateHome, ".android-imports"))) {
                throw new IOException("The selected folder uses a reserved name: .android-imports");
            }
            return result;
        }

        /** Keep both abandoned-file cleanup and new writes in the reserved directory. */
        private static File stagingDirectory(File stateHome) throws IOException {
            File expected = new File(stateHome, ".android-imports").getAbsoluteFile();
            File actual = expected.getCanonicalFile();
            LaunchConfig.requireInside(stateHome, actual);
            if (!actual.equals(expected)) {
                throw new IOException("The .android-imports folder must not be a symbolic link. "
                        + "Remove that link from the game folder and retry.");
            }
            return actual;
        }

        /** Stage on the same filesystem, then atomically install the complete file. */
        private void copyStream(InputStream input, File destination) throws IOException {
            makeDirectory(destination.getParentFile());
            File temp = new File(stagingDirectory(stateHome), UUID.randomUUID() + ".part");
            boolean installed = false;
            try {
                try (FileOutputStream output = new FileOutputStream(temp)) {
                    byte[] buffer = new byte[128 * 1024];
                    int count;
                    while ((count = input.read(buffer)) != -1) {
                        checkCancelled();
                        if (count == 0) continue;
                        output.write(buffer, 0, count);
                    }
                    output.getFD().sync();
                }
                checkCancelled();
                if (destination.exists()) throw new IOException("A resource appeared during setup: " + destination.getName());
                try {
                    // Both paths are in private internal storage. POSIX rename is atomic
                    // on this filesystem and is available through Os since API 21.
                    Os.rename(temp.getPath(), destination.getPath());
                } catch (ErrnoException error) {
                    throw new IOException("Could not install resource: " + destination.getName(), error);
                }
                installed = true;
            } finally {
                if (!installed) deleteIfExists(temp);
            }
        }
    }

    private static void deleteIfExists(File file) throws IOException {
        try {
            Os.remove(file.getPath());
        } catch (ErrnoException error) {
            if (error.errno != OsConstants.ENOENT) {
                throw new IOException("Could not remove temporary resource: " + file.getName(), error);
            }
        }
    }

    private static void makeDirectory(File directory) throws IOException {
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IOException("Cannot create game folder: " + directory.getName());
        }
    }

    private static final class Cancelled extends IOException {}
}
