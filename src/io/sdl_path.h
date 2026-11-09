// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef HYPSEUS_SDL_PATH_H
#define HYPSEUS_SDL_PATH_H

#include <string>
#ifdef __ANDROID__
#include <unistd.h>
#include <stdlib.h>
#endif

// SDL on Android treats relative file names as APK asset names, even after
// chdir(). Hypseus and Singe use normal filesystem paths, so make them absolute
// before crossing into SDL, SDL_image, SDL_ttf, or SDL_mixer. Resolve against
// the current directory so LuaFileSystem.chdir retains its normal meaning.
inline std::string sdl_file_path(const std::string &path)
{
#ifdef __ANDROID__
    if (!path.empty() && path[0] != '/' && path.compare(0, 10, "content://") != 0) {
        char directory[4096];
        if (getcwd(directory, sizeof(directory))) {
            return std::string(directory) + "/" + path;
        }
    }
#endif
    return path;
}

// Read-only support fallback. Keep writes and game-relative files on the normal
// filesystem; only the three bundled resource roots may resolve to APK assets.
inline std::string sdl_read_path(const std::string &path)
{
    const std::string file = sdl_file_path(path);
#ifdef __ANDROID__
    const bool resource = path.compare(0, 5, "pics/") == 0 ||
                          path.compare(0, 6, "fonts/") == 0 ||
                          path.compare(0, 6, "sound/") == 0;
    if (resource && path.find("/../") == std::string::npos &&
        path.find("/./") == std::string::npos && path.find('\\') == std::string::npos &&
        path.size() > 3 && path.compare(path.size() - 3, 3, "/..") != 0 &&
        !file.empty() && file[0] == '/' && access(file.c_str(), F_OK) != 0) {
        // Only bundled WAVs use a neutral suffix to allow APK ZIP compression.
        // External game files and write paths keep their original names.
        const bool wav = path.compare(0, 6, "sound/") == 0 && path.size() >= 4
                && path.compare(path.size() - 4, 4, ".wav") == 0;
        return "hypseus/" + path + (wav ? ".bin" : "");
    }
#endif
    return file;
}

#endif
