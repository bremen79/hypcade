// Android integration for the unofficial Android port. GPL-3.0-or-later.
#include <SDL3/SDL.h>
#include <jni.h>
#include <atomic>
#include "../../../src/io/input.h"

// Read the active Hypseus keymap instead of assuming desktop key defaults.
extern int g_key_defs[SWITCH_COUNT][2];
static int android_start_skill = 0;
static unsigned android_start_buttons = 0;
static SDL_Keycode android_skill_key = SDLK_UNKNOWN;

extern "C" JNIEXPORT void JNICALL
Java_org_hypseus_android_HypseusActivity_nativeConfigureStartSkill(JNIEnv *, jclass, jint skill)
{
    android_start_skill = skill >= 1 && skill <= 3 ? skill : 0;
}

// Queue the existing skill key before Start and release it with Start. This
// works for physical mappings, mobile controls and Watch Mode on the emulator
// thread, without changing game drivers or the global controller action IDs.
static void android_start_skill_input(int action, bool down)
{
    if (!android_start_skill || (action != 8 && action != 12)) return;
    const unsigned bit = action == 8 ? 1 : 2;
    if (down && (android_start_buttons & bit)) return;
    if (!down && !(android_start_buttons & bit)) return;
    if (down && !android_start_buttons) {
        android_skill_key = static_cast<SDL_Keycode>(g_key_defs[SWITCH_SKILL1 + android_start_skill - 1][0]);
        if (android_skill_key == SDLK_UNKNOWN)
            android_skill_key = static_cast<SDL_Keycode>(g_key_defs[SWITCH_SKILL1 + android_start_skill - 1][1]);
    }
    const bool transition = down ? !android_start_buttons : android_start_buttons == bit;
    android_start_buttons = down ? android_start_buttons | bit : android_start_buttons & ~bit;
    if (!transition || android_skill_key == SDLK_UNKNOWN) return;
    SDL_Event event = {};
    event.type = down ? SDL_EVENT_KEY_DOWN : SDL_EVENT_KEY_UP;
    event.key.key = android_skill_key;
    event.key.down = down;
    SDL_PushEvent(&event);
    if (!down) android_skill_key = SDLK_UNKNOWN;
}

static std::atomic<bool> android_emulator_ready{false};

extern "C" void hypseus_android_mark_emulator_ready()
{
    android_emulator_ready.store(true, std::memory_order_release);
}

extern "C" JNIEXPORT jboolean JNICALL
Java_org_hypseus_android_HypseusActivity_nativeEmulatorReady(JNIEnv *, jclass)
{
    return android_emulator_ready.load(std::memory_order_acquire) ? JNI_TRUE : JNI_FALSE;
}

// The Java overlay uses SDLActivity's official key methods, which update SDL's
// keyboard/modifier state as well as its event queue. Quit is queued so that
// only the emulator thread touches emulator state and performs its cleanup.
extern "C" JNIEXPORT void JNICALL
Java_org_hypseus_android_HypseusActivity_nativeQuit(JNIEnv *, jclass)
{
    if (SDL_WasInit(SDL_INIT_EVENTS) != 0) {
        SDL_Event event = {};
        event.type = SDL_EVENT_QUIT;
        SDL_PushEvent(&event);
    }
}

// Custom cabinet controls use logical switches, independent of hypinput.ini.
// SDL's queue transfers them to the emulator thread (never call game state here).
Uint32 hypseus_android_arcade_event_type()
{
    static const Uint32 type = SDL_RegisterEvents(1);
    return type;
}
extern "C" JNIEXPORT void JNICALL
Java_org_hypseus_android_HypseusActivity_nativeArcadeInput(JNIEnv *, jclass, jint action, jboolean down)
{
    if (action < 0 || action > 12 || SDL_WasInit(SDL_INIT_EVENTS) == 0) return;
    android_start_skill_input(action, down == JNI_TRUE);
    SDL_Event event = {};
    event.type = hypseus_android_arcade_event_type();
    if (!event.type) return;
    event.user.code = action;
    event.user.data1 = down ? reinterpret_cast<void *>(1) : nullptr;
    SDL_PushEvent(&event);
}

int hypseus_android_smoke_test()
{
    SDL_Window *window = NULL;
    SDL_Renderer *renderer = NULL;
    SDL_AudioStream *stream = NULL;
    bool ok = SDL_CreateWindowAndRenderer("Hypseus display and audio test", 640, 480,
                                         SDL_WINDOW_FULLSCREEN, &window, &renderer);
    if (ok) {
        SDL_AudioSpec spec = {};
        spec.format = SDL_AUDIO_F32;
        spec.channels = 2;
        spec.freq = 48000;
        stream = SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK, &spec, NULL, NULL);
        ok = stream != NULL && SDL_ResumeAudioStreamDevice(stream);
        if (ok) {
            const float silence[2048] = {};
            ok = SDL_PutAudioStreamData(stream, silence, sizeof(silence));
        }
    }
    if (ok) {
        SDL_SetRenderLogicalPresentation(renderer, 640, 480, SDL_LOGICAL_PRESENTATION_LETTERBOX);
        const Uint8 colors[6][3] = {{30, 190, 190}, {240, 190, 55}, {225, 90, 90},
                                   {60, 150, 230}, {160, 110, 220}, {80, 185, 100}};
        const Uint64 end = SDL_GetTicks() + 2000;
        bool stop = false;
        while (!stop && SDL_GetTicks() < end) {
            SDL_Event event;
            while (SDL_PollEvent(&event)) {
                if (event.type == SDL_EVENT_QUIT) stop = true;
            }
            SDL_SetRenderDrawColor(renderer, 16, 20, 28, 255);
            ok = SDL_RenderClear(renderer) && ok;
            for (int i = 0; i < 6; ++i) {
                SDL_FRect rect = {20.0f + i * 100.0f, 80.0f, 90.0f, 320.0f};
                SDL_SetRenderDrawColor(renderer, colors[i][0], colors[i][1], colors[i][2], 255);
                ok = SDL_RenderFillRect(renderer, &rect) && ok;
            }
            ok = SDL_RenderPresent(renderer) && ok;
            SDL_Delay(16);
        }
    }
    if (ok) SDL_Log("HYPSEUS_ANDROID_SMOKE PASS: renderer and audio device initialized");
    else SDL_LogError(SDL_LOG_CATEGORY_APPLICATION, "HYPSEUS_ANDROID_SMOKE FAIL: %s", SDL_GetError());
    SDL_DestroyAudioStream(stream);
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    return ok ? 0 : 1;
}

namespace video { void set_android_mobile_display(bool enabled); }
extern "C" JNIEXPORT void JNICALL
Java_org_hypseus_android_HypseusActivity_nativeConfigureDisplay(JNIEnv *, jclass, jboolean mobile)
{
    video::set_android_mobile_display(mobile);
}
