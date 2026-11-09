// ldv1000.h - the Pioneer LD-V1000 laserdisc player, as a game sees it.
//
// The LD-V1000 was built for arcade games. The game drives it over an 8-bit
// parallel link: it sends one command byte at a time and reads back a status
// byte. Frame numbers are sent as separate digit bytes, so "search to frame
// 1366" is the bytes 1, 3, 6, 6, SEARCH.
//
// Two strobe lines pace the conversation. While parked the player pulses
// them every 21 ms; once the disc is turning, once per video field (59.94
// times a second). First the status strobe: "my status byte is fresh, read
// it". Then, 54 microseconds later, the command strobe: "send me a byte".
//
// The player only accepts a command while bit 7 of its status (READY) is
// set. Accepting one clears READY, and the "no entry" byte FF sets it again,
// which is why games send FF between commands.
//
// This module is the protocol: status, digits and strobes. The mechanics
// of playing, pausing and searching are the plain player model in ldp.h.
// Behaviour follows MAME's LD-V1000 model (ldv1000hle.cpp, Ryan Holtz).

#ifndef LV_LDV1000_H
#define LV_LDV1000_H

#include "ldp/ldp.h"

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    Ldp *ldp;
    double clock_hz;      // rate of the "now" timestamps (the game's CPU clock)
    uint64_t last;        // time the player was last brought up to date

    uint8_t status;       // status byte; bit 7 = ready for a command
    uint8_t digits[8];    // digits of a number being entered
    int digit_count;
    int autostop_frame;   // AUTOSTOP target, or -1
    uint64_t resume_at;   // end of a timed STOP, or 0
    uint8_t status_before_stop;
    LdpState previous_state;
    bool audio[2];        // audio channel enables (AUDIO1, AUDIO2)
    bool muted;           // playing at a set speed, started from a standstill: no sound
    int reply_frame;      // GET FRAME NUMBER: the frame being reported
    int64_t reply_field;  // and the field its first digit is in, or -1
    uint8_t last_command; // the last byte taken (not NO ENTRY)

    // Badlands' player runs Konami's own version of the player's ROM. In
    // it a digit leaves the player ready (so a frame number can be sent a
    // digit a field, with no NO ENTRY between), and 20 then 31 skips back
    // 16 frames. Set after ldv1000_init.
    bool konami_rom;
} Ldv1000;

// Attach to a player model (already set up with ldp_init) and park it,
// ready for commands. clock_hz is the rate of the timestamps passed to the
// other functions.
void ldv1000_init(Ldv1000 *ld, Ldp *ldp, double clock_hz);

// Bring the player up to time now. Called automatically by the functions
// below; call it directly to keep the picture moving between commands.
void ldv1000_update(Ldv1000 *ld, uint64_t now);

uint8_t ldv1000_read_status(Ldv1000 *ld, uint64_t now);
void ldv1000_write(Ldv1000 *ld, uint64_t now, uint8_t byte);
bool ldv1000_status_strobe(Ldv1000 *ld, uint64_t now);
bool ldv1000_command_strobe(Ldv1000 *ld, uint64_t now);

// Can audio channel 0 or 1 be heard? (When the disc is playing at normal
// speed: the game can switch each channel off, and some ways of playing are
// silent.)
bool ldv1000_audio_on(const Ldv1000 *ld, int channel);

// Name of a command byte, for logging ("SEARCH", "7", ...), or NULL.
const char *ldv1000_command_name(uint8_t byte);

#endif
