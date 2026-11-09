// SPDX-License-Identifier: GPL-2.0-or-later
// VLDP index format, extracted from vldp_internal.h (Matt Ownby).
#ifndef VLDP_INDEX_FORMAT_H
#define VLDP_INDEX_FORMAT_H
#include <cstdint>
// this is which version of the .dat file format we are using
#define DAT_VERSION 3

// header for the .DAT files that are generated
struct dat_header {
    uint8_t version;     // which version of the DAT file this is
    uint8_t finished;    // whether the parse finished parsing or was interrupted
    uint8_t uses_fields; // whether the stream uses fields or frames
    uint64_t length;     // length of the m2v stream
};

#endif
