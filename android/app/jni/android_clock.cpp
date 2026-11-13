/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
// SPDX-License-Identifier: GPL-3.0-or-later
#include "android_clock.h"

#include <SDL3/SDL.h>
#include <mutex>

namespace {

std::mutex clock_mutex;
Uint64 suspended_total = 0;
Uint64 suspended_at = 0;
bool suspended = false;
bool watching = false;

// The caller holds clock_mutex. Keeping the completed suspension in the
// offset makes the first resumed tick equal to the last suspended tick.
void resume_clock()
{
    if (suspended) {
        suspended_total += SDL_GetTicks() - suspended_at;
        suspended = false;
    }
}

bool SDLCALL watch_lifecycle(void *, SDL_Event *event)
{
    switch (event->type) {
    case SDL_EVENT_WILL_ENTER_BACKGROUND: {
        std::lock_guard<std::mutex> lock(clock_mutex);
        if (!suspended) {
            suspended_at = SDL_GetTicks();
            suspended = true;
        }
        break;
    }
    case SDL_EVENT_DID_ENTER_FOREGROUND:
    case SDL_EVENT_QUIT:
    case SDL_EVENT_TERMINATING: {
        std::lock_guard<std::mutex> lock(clock_mutex);
        // Android may destroy a stopped Activity without resuming it first.
        // Shutdown timeouts must still advance in that case.
        resume_clock();
        break;
    }
    default:
        break;
    }
    // An event watcher observes events; it does not consume them.
    return true;
}

} // namespace

Uint64 hypseus_android_ticks(void)
{
    std::lock_guard<std::mutex> lock(clock_mutex);
    const Uint64 now = suspended ? suspended_at : SDL_GetTicks();
    return now - suspended_total;
}

bool hypseus_android_clock_install(void)
{
    {
        std::lock_guard<std::mutex> lock(clock_mutex);
        if (watching) {
            return true;
        }
        suspended_total = 0;
        suspended_at = 0;
        suspended = false;
    }

    // Do not hold clock_mutex while registering/removing an SDL callback.
    if (!SDL_AddEventWatch(watch_lifecycle, nullptr)) {
        return false;
    }

    std::lock_guard<std::mutex> lock(clock_mutex);
    watching = true;
    return true;
}

void hypseus_android_clock_remove(void)
{
    {
        std::lock_guard<std::mutex> lock(clock_mutex);
        if (!watching) {
            return;
        }
        watching = false;
    }

    SDL_RemoveEventWatch(watch_lifecycle, nullptr);

    std::lock_guard<std::mutex> lock(clock_mutex);
    resume_clock();
}
