#include "util/zip.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <zlib.h>

// Zip files store numbers little-endian.
static uint32_t get16(const uint8_t *p) { return (uint32_t)(p[0] | (p[1] << 8)); }
static uint32_t get32(const uint8_t *p) { return get16(p) | (get16(p + 2) << 16); }

static bool names_match(const uint8_t *entry, size_t entry_len, const char *name)
{
    if (strlen(name) != entry_len) return false;
    for (size_t i = 0; i < entry_len; i++)
        if (tolower(entry[i]) != tolower((unsigned char)name[i])) return false;
    return true;
}

static uint8_t *read_whole_file(const char *path, size_t *size)
{
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long len = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *buf = len > 0 ? malloc((size_t)len) : NULL;
    if (buf && fread(buf, 1, (size_t)len, f) != (size_t)len) {
        free(buf);
        buf = NULL;
    }
    fclose(f);
    *size = buf ? (size_t)len : 0;
    return buf;
}

bool zip_read_file(const char *zip_path, const char *name,
                   uint8_t **data, size_t *size, uint32_t *crc)
{
    size_t zip_size;
    uint8_t *zip = read_whole_file(zip_path, &zip_size);
    if (!zip) return false;
    bool ok = false;

    // The "end of central directory" record is the last thing in the file
    // (possibly followed by a comment of up to 64 KB), so search backwards
    // for its signature.
    const uint8_t *end = NULL;
    if (zip_size < 22) goto done;
    size_t lowest = zip_size > 22 + 0xFFFF ? zip_size - 22 - 0xFFFF : 0;
    for (size_t i = zip_size - 22 + 1; i-- > lowest;) {
        if (get32(zip + i) == 0x06054B50) {
            end = zip + i;
            break;
        }
    }
    if (!end) goto done;

    uint32_t entries = get16(end + 10);
    uint32_t dir_offset = get32(end + 16);

    // Walk the central directory looking for our file.
    const uint8_t *entry = zip + dir_offset;
    for (uint32_t n = 0; n < entries; n++) {
        if (entry + 46 > zip + zip_size || get32(entry) != 0x02014B50) goto done;
        uint32_t method = get16(entry + 10);
        uint32_t entry_crc = get32(entry + 16);
        uint32_t packed_size = get32(entry + 20);
        uint32_t full_size = get32(entry + 24);
        uint32_t name_len = get16(entry + 28);
        uint32_t extra_len = get16(entry + 30);
        uint32_t comment_len = get16(entry + 32);
        uint32_t local_offset = get32(entry + 42);

        if (names_match(entry + 46, name_len, name)) {
            // The file's data follows its "local header", which repeats the
            // name and may have a different-sized extra field.
            const uint8_t *local = zip + local_offset;
            if (local + 30 > zip + zip_size || get32(local) != 0x04034B50) goto done;
            const uint8_t *packed = local + 30 + get16(local + 26) + get16(local + 28);
            if (packed + packed_size > zip + zip_size) goto done;

            uint8_t *out = malloc(full_size ? full_size : 1);
            if (method == 0) {  // stored
                memcpy(out, packed, full_size);
            } else if (method == 8) {  // deflate
                z_stream zs = {0};
                zs.next_in = (Bytef *)packed;
                zs.avail_in = packed_size;
                zs.next_out = out;
                zs.avail_out = full_size;
                // Negative window bits: raw deflate data, no zlib header.
                if (inflateInit2(&zs, -MAX_WBITS) != Z_OK) { free(out); goto done; }
                int ret = inflate(&zs, Z_FINISH);
                inflateEnd(&zs);
                if (ret != Z_STREAM_END || zs.total_out != full_size) { free(out); goto done; }
            } else {
                fprintf(stderr, "zip: %s uses unsupported compression method %u\n", name, method);
                free(out);
                goto done;
            }
            *data = out;
            *size = full_size;
            *crc = entry_crc;
            ok = true;
            goto done;
        }
        entry += 46 + name_len + extra_len + comment_len;
    }

done:
    free(zip);
    return ok;
}
