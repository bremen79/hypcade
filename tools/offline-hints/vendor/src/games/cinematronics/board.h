// board.h - the Cinematronics laserdisc game board (US version, Pioneer
// LD-V1000), which runs Dragon's Lair and Space Ace.
//
// The board is small: a Z80 CPU at 4 MHz, 40 KB of ROM space (most sets
// use 32 KB), 2 KB of RAM, an AY-3-8910 sound chip (which also reads
// the DIP switches), the joystick and buttons, a 16-digit score display, and
// an 8-bit parallel link to the laserdisc player. A timer interrupts the CPU
// about 30.5 times a second.
//
// The game's whole world is in its address space:
//
//     0000-9FFF  ROM
//     A000-A7FF  RAM (repeated through BFFF)
//     C000-DFFF  inputs: read from C000 + (sound chip, joystick, coins/
//                start and player strobes, laserdisc data) * 8
//     E000-FFFF  outputs: sound chip, misc latch, laserdisc data, score
//                display digits
//
// Details come from the schematics as documented in MAME's dlair.cpp.

#ifndef LV_CINE_BOARD_H
#define LV_CINE_BOARD_H

#include "audio/ay8910.h"
#include "cpu/z80.h"
#include "ldp/ldv1000.h"

#include <stdbool.h>
#include <stdint.h>

#define CINE_CPU_HZ 4000000
#define CINE_SOUND_CHIP_HZ 2000000  // the AY-3-8910 runs at 16 MHz / 8
#define CINE_SAMPLE_RATE 44100      // rate of the sound chip's output samples

// The games on this board.
typedef enum {
    CINE_DRAGONS_LAIR,
    CINE_SPACE_ACE,
} CineGame;

// The game's name, for the window title: "Dragon's Lair" or "Space Ace".
const char *cine_game_name(CineGame game);

// The DIP switches: two banks of eight, DSW1 (A:1-8) and DSW2 (B:1-8), bit 0
// first. What each switch does depends on the ROM set. Dragon's Lair and
// all the fan sets share one layout; the original Space Ace has its own.
// (The fan sets' readmes give the physical switch positions instead,
// numbered 0-7: a bit set is a switch OFF.)
//
// These settings exist in every set, wherever its switches put them:
typedef enum {
    // The game always has two credits, so start works without coins.
    CINE_FREE_PLAY,
    // The hero still dies but never loses a life, so a player can see the
    // whole game.
    CINE_UNLIMITED_LIVES,
    // On (as the factory set it), the attract mode is mostly quiet: the game
    // switches the disc's sound off and only lets it through one attract
    // cycle in eight. Off: the attract mode always has sound.
    CINE_QUIET_ATTRACT,
} CineSetting;

// Where a set's switches put the settings above (see board.c).
typedef struct CineSwitchLayout CineSwitchLayout;

// How the board talks to the laserdisc player. The player drives two
// strobe lines that tell the game when to read status and when to send
// the next command byte. Every call passes the current time ("now", in CPU
// clock cycles since power-on) so the player can bring itself up to date.
typedef struct {
    void *ctx;
    uint8_t (*read_status)(void *ctx, uint64_t now);              // byte at C020
    void (*send_command)(void *ctx, uint64_t now, uint8_t byte);  // byte latched to the player
    bool (*status_strobe)(void *ctx, uint64_t now);  // true while the strobe is active
    bool (*command_strobe)(void *ctx, uint64_t now);
} CineLaserdisc;

// Space Ace's skill-level lamps, beside the skill buttons (see board.c).
#define CINE_LAMP_CADET 0x01
#define CINE_LAMP_CAPTAIN 0x02
#define CINE_LAMP_ACE 0x04

// Inputs are active low on the real board; here, true means pressed.
// Space Ace adds three skill-level buttons, chosen at the start of a game.
typedef struct {
    bool up, down, left, right, sword;
    bool start1, start2, coin1, coin2;
    bool cadet, captain, ace;
} CineInputs;

typedef struct {
    CineGame game;           // which game the ROMs hold (set by cine_load_roms)
    const CineSwitchLayout *switches;  // and where its settings are

    Z80 cpu;
    uint8_t rom[0xA000];
    uint8_t ram[0x800];

    uint8_t dsw1, dsw2;      // DIP switches (read through the sound chip)
    CineInputs inputs;
    CineLaserdisc laserdisc;

    Ay8910 ay;               // the sound chip
    uint8_t ay_select;       // sound chip register selected by the CPU
    uint8_t ld_latch;        // byte waiting to be sent to the player
    uint8_t misc;            // last value written to the misc latch
    uint8_t digits[16];      // score display: 0-9, 10-14 = A b C d E, 15 = blank
    uint8_t lamps;           // Space Ace's skill-level lamps (CINE_LAMP_*) that are lit

    uint64_t cycles;         // CPU clock cycles since power-on
    uint64_t next_irq;
} CineBoard;

// Load the ROMs from a zip file or a folder of .bin files. This works out
// which set they are (which game, which revision, or a fan-made set), checks
// each chip's checksum, and sets the DIP switches as that set expects.
// Returns false (after printing why) if it finds no set it can run.
bool cine_load_roms(CineBoard *board, const char *path);

// Does path hold a ROM set for this board (even one it can't run)? Quiet:
// for choosing a board before loading.
bool cine_recognizes(const char *path);

// Turn a setting on or off by flipping its DIP switch, as an operator would
// before switching the machine on.
void cine_set(CineBoard *board, CineSetting setting, bool on);
bool cine_get(const CineBoard *board, CineSetting setting);

// The same while the game runs. The games read their switches at power-up
// and keep a copy in RAM (DSW1 at A010, DSW2 at A011), so this changes the
// copy too.
void cine_set_now(CineBoard *board, CineSetting setting, bool on);

// A laserdisc link to an LD-V1000 model, the player this board was built for.
CineLaserdisc cine_ldv1000_link(Ldv1000 *player);

// Power on: reset the CPU. (The DIP switches stay as they are.)
void cine_reset(CineBoard *board, CineLaserdisc laserdisc);

// Run the board for (at least) the given number of CPU cycles.
void cine_run(CineBoard *board, uint64_t cycles);

#endif
