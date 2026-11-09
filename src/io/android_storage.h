// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef HYPSEUS_ANDROID_STORAGE_H
#define HYPSEUS_ANDROID_STORAGE_H
#ifdef __ANDROID__
#include <string>
#include <vector>
#include <sstream>
#include <iomanip>
#include <unistd.h>
#include <stdint.h>
#include <stdlib.h>

inline std::string android_absolute_path(const std::string &path) {
    char cwd[4096];
    std::string full = path;
    if (full.empty() || full[0] != '/') {
        if (!getcwd(cwd, sizeof(cwd))) return std::string();
        full = std::string(cwd) + "/" + full;
    }
    std::vector<std::string> parts;
    std::istringstream stream(full);
    std::string part, result;
    while (std::getline(stream, part, '/')) {
        if (part.empty() || part == ".") continue;
        if (part == "..") { if (!parts.empty()) parts.pop_back(); }
        else parts.push_back(part);
    }
    for (const auto &item : parts) result += "/" + item;
    return result.empty() ? "/" : result;
}

// Stable compact names keep long SD paths out of the engine's small path buffers.
inline std::string android_path_key(const std::string &path) {
    uint64_t hash = UINT64_C(14695981039346656037);
    for (unsigned char c : path) { hash ^= c; hash *= UINT64_C(1099511628211); }
    std::ostringstream key;
    key << std::hex << std::setfill('0') << std::setw(16) << hash;
    return key.str();
}
#endif
#endif
