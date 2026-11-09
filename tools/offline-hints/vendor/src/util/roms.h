// roms.h - read ROM chip images from a ROM set.
//
// A ROM set is either a zip file holding one file per chip (as arcade ROM
// sets are usually distributed) or a folder of the same files.

#ifndef LV_ROMS_H
#define LV_ROMS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// Read the chip called name from the set at path into a newly allocated
// buffer, which the caller frees. Returns false if it isn't there.
bool roms_read(const char *path, const char *name, uint8_t **data, size_t *size);

// Is the chip called name in the set at path?
bool roms_has(const char *path, const char *name);

// Look for the chip called name in the other zip files in the same folder
// as the set at path (for a set missing a chip it shares with another).
// On success, puts that zip's path in out and returns true.
bool roms_find_nearby(const char *path, const char *name, char *out, size_t size);

#endif
