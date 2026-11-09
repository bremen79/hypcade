// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef HYPCADE_ANDROID_INDEX_H
#define HYPCADE_ANDROID_INDEX_H
#include "index_format.h"
#include "../io/android_storage.h"
#include <sys/stat.h>
#include <cstdlib>
#include <cstdio>
#include <cstdint>
#include <string>
#include <vector>
#include <unistd.h>

// Check the entire table, not just its presence or header. -1 marks non-I frames.
template<class Header>
bool android_index_valid(FILE *file, uint64_t media_size, unsigned version, unsigned max_frames)
{
    Header header{};
    rewind(file);
    if (fread(&header, sizeof(header), 1, file) != 1 || header.version != version ||
        header.finished != 1 || header.uses_fields > 1 || header.length != media_size) return false;
    unsigned frames = 0;
    bool has_keyframe = false;
    uint64_t offset;
    size_t bytes;
    while ((bytes = fread(&offset, 1, sizeof(offset), file)) != 0) {
        if (bytes != sizeof(offset) || ++frames > max_frames) return false;
        if (offset != UINT64_MAX) {
            if (offset >= media_size) return false;
            has_keyframe = true;
        }
    }
    return !ferror(file) && frames && has_keyframe;
}

inline std::string android_index_cache(const std::string &media, uint64_t size,
                                       const std::string &home)
{
    struct stat info = {};
    stat(media.c_str(), &info);
    return home + "/indexes/" + android_path_key(android_absolute_path(media) + ":" +
        std::to_string(size) + ":" + std::to_string(info.st_mtime)) + ".dat";
}
inline bool android_index_file_valid(const std::string &name, uint64_t size)
{
    FILE *file = fopen(name.c_str(), "rb");
    if (!file) return false;
    bool valid = android_index_valid<dat_header>(file, size, DAT_VERSION, 512000);
    fclose(file);
    return valid;
}
inline bool android_video_index_ready(const std::string &media, const std::string &home)
{
    struct stat info = {};
    if (media.size() < 3 || stat(media.c_str(), &info) != 0 || info.st_size <= 0) return false;
    return android_index_file_valid(media.substr(0, media.size()-3) + "dat", info.st_size) ||
           android_index_file_valid(android_index_cache(media, info.st_size, home), info.st_size);
}

// Stage beside the destination; failure leaves any existing index untouched.
template<class Generate>
bool android_index_publish(const std::string &destination, Generate generate)
{
    std::string pattern = destination + ".tmp-XXXXXX";
    std::vector<char> path(pattern.begin(), pattern.end());
    path.push_back('\0');
    int fd = mkstemp(path.data());
    if (fd < 0) return false;
    close(fd);
    bool ok = generate(path.data());
    if (ok) ok = rename(path.data(), destination.c_str()) == 0;
    if (!ok) remove(path.data());
    return ok;
}
#endif
