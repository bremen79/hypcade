#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
"""Exercise the production suspend clock with deterministic SDL boundaries.

No Android SDK or downloaded dependencies are required. The test compiles the
actual android_clock.cpp; only SDL's monotonic clock and event-registration
functions are replaced. Run: python3 android/tests/test_android_clock.py
"""

from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]
JNI = ROOT / "android" / "app" / "jni"

STDINC = """\
#pragma once
#include <cstdint>
using Uint64 = std::uint64_t;
using Uint32 = std::uint32_t;
#define SDLCALL
"""

SDL_HEADER = """\
#pragma once
#include "SDL_stdinc.h"
enum {
    SDL_EVENT_WILL_ENTER_BACKGROUND = 1,
    SDL_EVENT_DID_ENTER_BACKGROUND,
    SDL_EVENT_WILL_ENTER_FOREGROUND,
    SDL_EVENT_DID_ENTER_FOREGROUND,
    SDL_EVENT_QUIT,
    SDL_EVENT_TERMINATING,
    SDL_EVENT_OTHER
};
struct SDL_Event { Uint32 type; };
using SDL_EventFilter = bool (SDLCALL *)(void *, SDL_Event *);
Uint64 SDL_GetTicks(void);
void SDL_Delay(Uint32);
bool SDL_AddEventWatch(SDL_EventFilter, void *);
void SDL_RemoveEventWatch(SDL_EventFilter, void *);
"""

HARNESS = r"""
#include "android_clock.h"
#include "timer.h"
#include <atomic>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

std::atomic<Uint64> wall_time{100};
SDL_EventFilter watcher = nullptr;
void *watcher_data = nullptr;
bool fail_registration = false;
int registrations = 0;

Uint64 SDL_GetTicks(void) { return wall_time.load(); }
void SDL_Delay(Uint32) {}
bool SDL_AddEventWatch(SDL_EventFilter callback, void *data) {
    ++registrations;
    if (fail_registration) return false;
    watcher = callback;
    watcher_data = data;
    return true;
}
void SDL_RemoveEventWatch(SDL_EventFilter callback, void *data) {
    if (callback != watcher || data != watcher_data) {
        throw std::runtime_error("Removed the wrong SDL event watcher");
    }
    watcher = nullptr;
    watcher_data = nullptr;
}
void event(Uint32 type) {
    if (!watcher) throw std::runtime_error("No event watcher registered");
    SDL_Event e{type};
    if (!watcher(watcher_data, &e)) {
        throw std::runtime_error("Lifecycle watcher consumed an SDL event");
    }
}
void expect(Uint64 actual, Uint64 wanted, const char *label) {
    if (actual != wanted) {
        throw std::runtime_error(std::string(label) + ": got " +
                                 std::to_string(actual) + ", expected " +
                                 std::to_string(wanted));
    }
}
void check(bool condition, const char *label) {
    if (!condition) throw std::runtime_error(label);
}

int main() {
    expect(GET_TICKS(), 100, "Before clock installation");
    fail_registration = true;
    check(!hypseus_android_clock_install(), "Registration failure was hidden");
    hypseus_android_clock_remove();
    expect(GET_TICKS(), 100, "Failed installation changed application time");
    fail_registration = false;
    check(hypseus_android_clock_install(), "Installation failed");
    const int count = registrations;
    check(hypseus_android_clock_install(), "Repeated installation failed");
    expect(registrations, count, "Duplicate watcher registration");

    wall_time = 250;
    expect(GET_TICKS(), 250, "Foreground clock");
    event(SDL_EVENT_WILL_ENTER_BACKGROUND);
    wall_time = 10000;
    expect(GET_TICKS(), 250, "Suspended clock advanced");
    event(SDL_EVENT_WILL_ENTER_BACKGROUND);
    event(SDL_EVENT_DID_ENTER_BACKGROUND);
    wall_time = 20000;
    expect(GET_TICKS(), 250, "Duplicate pause changed suspended clock");
    event(SDL_EVENT_WILL_ENTER_FOREGROUND);
    expect(GET_TICKS(), 250, "Clock resumed before foreground completed");
    event(SDL_EVENT_DID_ENTER_FOREGROUND);
    expect(GET_TICKS(), 250, "Resume jumped application time");
    wall_time = 20060;
    expect(GET_TICKS(), 310, "Resumed clock did not advance");
    wall_time = 20070;
    event(SDL_EVENT_DID_ENTER_FOREGROUND);
    event(SDL_EVENT_OTHER);
    expect(GET_TICKS(), 320, "Duplicate/unrelated event changed offset");

    wall_time = 20100;
    event(SDL_EVENT_WILL_ENTER_BACKGROUND);
    wall_time.fetch_add((Uint64(1) << 32) + 60);
    expect(GET_TICKS(), 350, "Long suspension overflowed");
    event(SDL_EVENT_DID_ENTER_FOREGROUND);
    expect(GET_TICKS(), 350, "Long suspension was not excluded");
    wall_time.fetch_add(25);
    expect(GET_TICKS(), 375, "64-bit clock failed after long suspension");

    event(SDL_EVENT_WILL_ENTER_BACKGROUND);
    wall_time.fetch_add(5000);
    event(SDL_EVENT_QUIT);
    expect(GET_TICKS(), 375, "Quit jumped application time");
    wall_time.fetch_add(10);
    expect(GET_TICKS(), 385, "Quit left shutdown deadlines frozen");
    event(SDL_EVENT_WILL_ENTER_BACKGROUND);
    wall_time.fetch_add(2000);
    event(SDL_EVENT_TERMINATING);
    wall_time.fetch_add(20);
    expect(GET_TICKS(), 405, "Termination left shutdown deadlines frozen");

    event(SDL_EVENT_WILL_ENTER_BACKGROUND);
    wall_time.fetch_add(900);
    hypseus_android_clock_remove();
    check(watcher == nullptr, "Removal retained event watcher");
    wall_time.fetch_add(20);
    expect(GET_TICKS(), 425, "Removal left clock suspended");
    hypseus_android_clock_remove();

    // Multiple readers emulate main, VLDP and audio threads. All observe a
    // nondecreasing clock while the lifecycle owner suspends/resumes it.
    check(hypseus_android_clock_install(), "Reinstallation failed");
    const Uint64 before = GET_TICKS();
    std::atomic<bool> done{false};
    std::atomic<bool> monotonic{true};
    std::vector<std::thread> readers;
    for (int i = 0; i < 3; ++i) {
        readers.emplace_back([&]() {
            Uint64 previous = GET_TICKS();
            while (!done.load()) {
                const Uint64 current = GET_TICKS();
                if (current < previous) monotonic = false;
                previous = current;
            }
        });
    }
    for (int i = 0; i < 2000; ++i) {
        wall_time.fetch_add(3);
        event(SDL_EVENT_WILL_ENTER_BACKGROUND);
        wall_time.fetch_add(10000);
        event(SDL_EVENT_DID_ENTER_FOREGROUND);
        wall_time.fetch_add(1);
    }
    done = true;
    for (auto &reader : readers) reader.join();
    check(monotonic.load(), "Concurrent reads observed time going backwards");
    expect(GET_TICKS(), before + 8000, "Repeated suspensions accumulated drift");
    hypseus_android_clock_remove();
    std::cout << "Android clock lifecycle and concurrent-reader checks passed\n";
}
"""

DESKTOP_HARNESS = r"""
#include "timer.h"
Uint64 SDL_GetTicks(void) { return 42; }
int main() {
    return GET_TICKS() == 42 ? 0 : 1;
}
"""


class AndroidClockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
        if not cls.compiler:
            raise unittest.SkipTest("A C++11 host compiler is required")

    def compile_and_run(self, source, *, android):
        with tempfile.TemporaryDirectory(prefix="hypseus-clock-test-") as directory:
            path = Path(directory)
            (path / "SDL3").mkdir()
            (path / "SDL3" / "SDL_stdinc.h").write_text(STDINC)
            (path / "SDL3" / "SDL.h").write_text(SDL_HEADER)
            (path / "test.cpp").write_text(textwrap.dedent(source))
            executable = path / "clock-test"
            command = [
                self.compiler, "-std=c++11", "-pthread", "-Wall", "-Wextra", "-Werror",
                "-I", str(path), "-I", str(JNI), "-I", str(ROOT / "src" / "timer"),
                str(path / "test.cpp"), "-o", str(executable),
            ]
            if android:
                command += ["-D__ANDROID__", str(JNI / "android_clock.cpp")]
            build = subprocess.run(command, text=True, capture_output=True, timeout=60)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            result = subprocess.run([str(executable)], text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_android_lifecycle_and_concurrent_readers(self):
        self.compile_and_run(HARNESS, android=True)

    def test_desktop_clock_unchanged(self):
        self.compile_and_run(DESKTOP_HARNESS, android=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
