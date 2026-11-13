/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* Hypcade modification notice (2026-11-08): modified for Android arcade
 * integration. See android/MODIFICATIONS.md. Original notices are retained below. */
/*
* ____ DAPHNE COPYRIGHT NOTICE ____
*
* Copyright (C) 2023 DirtBagXon
*
* This file is part of DAPHNE, a laserdisc arcade game emulator
*
* DAPHNE is free software; you can redistribute it and/or modify
* it under the terms of the GNU General Public License as published by
* the Free Software Foundation; either version 2 of the License, or
* (at your option) any later version.
*
* DAPHNE is distributed in the hope that it will be useful,
* but WITHOUT ANY WARRANTY; without even the implied warranty of
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
* GNU General Public License for more details.
*
* You should have received a copy of the GNU General Public License
* along with this program; if not, write to the Free Software
* Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
*/

/*
* This is SINGE - the Somewhat Interactive Nostalgic Game Engine!
*/

#include <string>
#include "../singe.h"
#include "../../io/homedir.h"
#ifdef __ANDROID__
#include "../../io/android_storage.h"
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <sys/stat.h>
#endif

bool net_send_enabled();

extern "C" {

const char* get_romdir_path()
{
    static std::string romdir = g_homedir.get_romdir();
    romdir = romdir.empty() ? "roms" : romdir;

    return romdir.c_str();
}

const char* get_ramdir_path()
{
    static std::string dir = [] {
        std::string ramdir = g_homedir.get_ramdir();
        if (ramdir.empty()) ramdir = "ram";
        return ramdir + "/";
    }();

    return dir.c_str();
}

#ifdef __ANDROID__
// Script settings are overlays in private storage; reads fall back to the source.
int android_save_path(const char *source, char *output, size_t size)
{
    std::string path = android_absolute_path(source);
    std::string ram = get_ramdir_path();
    std::string result = path.compare(0, ram.size(), ram) == 0 ? path :
        ram + android_path_key(path) + ".save";
    if (result.size() >= size) { errno = ENAMETOOLONG; return -1; }
    memcpy(output, result.c_str(), result.size() + 1);
    return 0;
}

FILE *android_script_fopen(const char *source, const char *mode)
{
    char saved[4096];
    if (android_save_path(source, saved, sizeof(saved)) != 0) return NULL;
    bool writing = strpbrk(mode, "wa+") != NULL;
    if (writing) {
        // Preserve small source settings when a script appends or updates them.
        // Never seed a private copy of a large media file.
        if ((mode[0] == 'a' || strchr(mode, '+')) && access(saved, F_OK) != 0) {
            struct stat original = {};
            if (stat(source, &original) == 0 && S_ISREG(original.st_mode)) {
                if (original.st_size > 1024 * 1024) { errno = EFBIG; return NULL; }
                FILE *input = fopen(source, "rb");
                if (!input) return NULL;
                FILE *output = fopen(saved, "wb");
                if (!output) { fclose(input); return NULL; }
                char buffer[8192];
                size_t count;
                bool ok = true;
                while ((count = fread(buffer, 1, sizeof(buffer), input)) != 0) {
                    if (fwrite(buffer, 1, count, output) != count) { ok = false; break; }
                }
                if (ferror(input)) ok = false;
                fclose(input);
                if (fclose(output) != 0) ok = false;
                if (!ok) { remove(saved); errno = EIO; return NULL; }
            }
        }
        return fopen(saved, mode);
    }
    FILE *file = fopen(saved, mode);
    return file ? file : fopen(source, mode);
}
#endif

unsigned char socket_disabled()
{
    return net_send_enabled() ? 0 : 1;
}

}

int singe::scoreboard_format(int value)
{
    uint8_t digit;

    switch (value) {
    case -1:
       digit = 0xf; // off
       break;
    case -2:
       digit = 0xa; // -
       break;
    case -3:
       if (g_bezelboard.type == SINGE_SB_USB)
           digit = 0xf;
       else
           digit = 0xb; // blank
       break;
    case -4:
       digit = 0xc; // H
       break;
    case -5:
       digit = 0xd; // A
       break;
    default:
       digit = 0;
       break;
    }
    return digit;
}

void singe::scoreboard_score(int value, uint8_t player)
{
    uint8_t digit;
    const uint8_t which = (6 - 1); // six chars
    for (int i = which; i >= 0; i--) {
        if (value < 0)
            digit = scoreboard_format(value);
        else
        {
            digit = value % 10;
            value = value / 10;
        }
        m_pScoreboard->update_player_score(i, digit, player);
    }
}

void singe::scoreboard_lives(int value, uint8_t player)
{
    uint8_t digit;

    if (value < 0) digit = scoreboard_format(value);
    else digit = value % 10;

    m_pScoreboard->update_player_lives(digit, player);
}

void singe::scoreboard_credits(uint8_t value)
{
    const uint8_t which = (2 - 1); // two chars
    for (int i = which; i >= 0; i--) {
        uint8_t digit = value % 10;
        value = value / 10;
        m_pScoreboard->update_credits(i, digit);
    }
}
