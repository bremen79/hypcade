#include "util/roms.h"
#include "util/zip.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// ROM chips are small; nothing in a set is bigger than this.
#define MAX_CHIP_SIZE 0x10000

static bool ends_with_zip(const char *path)
{
    size_t n = strlen(path);
    return n >= 4 && (strcmp(path + n - 4, ".zip") == 0 || strcmp(path + n - 4, ".ZIP") == 0);
}

bool roms_read(const char *path, const char *name, uint8_t **data, size_t *size)
{
    uint32_t zip_crc;
    if (ends_with_zip(path)) return zip_read_file(path, name, data, size, &zip_crc);

    char file[1024];
    snprintf(file, sizeof file, "%s/%s", path, name);
    FILE *f = fopen(file, "rb");
    if (!f) return false;
    *data = malloc(MAX_CHIP_SIZE);
    *size = fread(*data, 1, MAX_CHIP_SIZE, f);
    fclose(f);
    return true;
}

bool roms_has(const char *path, const char *name)
{
    uint8_t *data = NULL;
    size_t size;
    if (!roms_read(path, name, &data, &size)) return false;
    free(data);
    return true;
}

// The folder a set is in, with its separator ("" for the current folder).
static void folder_of(const char *path, char *out, size_t size)
{
    const char *slash = strrchr(path, '/'), *backslash = strrchr(path, '\\');
    if (backslash > slash) slash = backslash;
    snprintf(out, size, "%.*s", slash ? (int)(slash - path + 1) : 0, path);
}

#ifdef _WIN32
#include <io.h>

bool roms_find_nearby(const char *path, const char *name, char *out, size_t size)
{
    char folder[1024], pattern[1100];
    folder_of(path, folder, sizeof folder);
    snprintf(pattern, sizeof pattern, "%s*.zip", folder);
    struct _finddata_t found;
    intptr_t h = _findfirst(pattern, &found);
    if (h == -1) return false;
    bool ok = false;
    do {
        snprintf(out, size, "%s%s", folder, found.name);
        if (strcmp(out, path) != 0 && roms_has(out, name)) ok = true;
    } while (!ok && _findnext(h, &found) == 0);
    _findclose(h);
    return ok;
}
#else
#include <dirent.h>

bool roms_find_nearby(const char *path, const char *name, char *out, size_t size)
{
    char folder[1024];
    folder_of(path, folder, sizeof folder);
    DIR *d = opendir(folder[0] ? folder : ".");
    if (!d) return false;
    bool ok = false;
    struct dirent *e;
    while (!ok && (e = readdir(d)) != NULL) {
        if (!ends_with_zip(e->d_name)) continue;
        snprintf(out, size, "%s%s", folder, e->d_name);
        if (strcmp(out, path) != 0 && roms_has(out, name)) ok = true;
    }
    closedir(d);
    return ok;
}
#endif
