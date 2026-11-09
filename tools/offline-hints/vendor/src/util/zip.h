// zip.h - read a file out of a .zip archive.
//
// Arcade ROM sets are traditionally distributed as zip files, one file per
// ROM chip. A zip file ends with a "central directory" listing each file's
// name, size, checksum and where its data starts; the data itself is either
// stored as-is or compressed with "deflate". We find the entry by name in
// the directory and let zlib undo the deflate.

#ifndef LV_ZIP_H
#define LV_ZIP_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// Read the file called name (case-insensitive) from the zip archive at
// zip_path into a newly allocated buffer. On success, *data must be freed
// by the caller and *crc holds the CRC-32 recorded in the archive.
bool zip_read_file(const char *zip_path, const char *name,
                   uint8_t **data, size_t *size, uint32_t *crc);

#endif
