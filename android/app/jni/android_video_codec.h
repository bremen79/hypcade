/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <cstdint>
#include <cstddef>
bool android_video_start(const char *path, uint64_t offset, const uint8_t *header, size_t header_size, int width, int height);
const uint8_t *android_video_next(int first_temporal_reference);
void android_video_close();
void android_video_disable();
