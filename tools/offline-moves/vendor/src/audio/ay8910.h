// ay8910.h - the General Instrument AY-3-8910 sound chip.
//
// The AY-3-8910 (1978) makes sound for countless computers and arcade
// boards. It has three square-wave tone generators (A, B, C), one noise
// generator, and an envelope generator that can shape the volume over time.
// The CPU controls it through 16 registers:
//
//     R0-R5   tone period for A, B, C (12 bits each: fine, coarse)
//     R6      noise period (5 bits)
//     R7      mixer: bits 0-2 turn tone off for A-C, bits 3-5 noise;
//             bits 6-7 set the two I/O ports as inputs (0) or outputs (1)
//     R8-R10  volume for A, B, C (0-15), or bit 4 set: use the envelope
//     R11-R12 envelope period (16 bits)
//     R13     envelope shape (writing it restarts the envelope)
//     R14-R15 the two 8-bit I/O ports (on the Cinematronics board, the DIP switches)
//
// A tone channel's frequency is clock / (16 * period). The chip is emulated
// at its internal rate (clock / 8) and the result averaged down to the
// output sample rate.
//
// Writes are stamped with the CPU's clock so the sound changes at exactly
// the right moment: before each write, sound is generated up to that time.

#ifndef LV_AY8910_H
#define LV_AY8910_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint8_t regs[16];

    // Clocks: timestamps are in CPU cycles; the chip runs at chip_hz.
    double ticks_per_cycle;   // chip ticks (chip_hz / 8) per CPU cycle
    double samples_per_tick;  // output samples per chip tick
    uint64_t time;            // CPU cycle the chip has been run up to
    double tick_carry;        // fraction of a tick left over

    // Generators.
    uint16_t tone_count[3];
    bool tone_high[3];
    uint8_t noise_count;
    uint32_t noise_shift;     // 17-bit shift register
    uint16_t envelope_count;
    uint8_t envelope_step;    // 0-15 within the current ramp
    bool envelope_rising;
    bool envelope_holding;
    uint8_t envelope_hold_level;
    bool half_tick;           // noise and envelope run at half the tone rate

    // Output.
    bool rendering;           // generate samples (off: just keep the registers)
    double mix_sum;           // sum of outputs since the last sample
    int mix_count;
    double sample_phase;
    float dc_in, dc_out;      // DC-blocking filter state
    float *samples;           // generated, not yet taken
    int sample_count, sample_capacity;
} Ay8910;

// cpu_hz: rate of the timestamps. chip_hz: the chip's clock. sample_rate:
// output rate. The chip starts silent, not rendering.
void ay8910_init(Ay8910 *ay, double cpu_hz, double chip_hz, double sample_rate);
void ay8910_free(Ay8910 *ay);

void ay8910_write(Ay8910 *ay, uint64_t now, int reg, uint8_t value);
uint8_t ay8910_read(const Ay8910 *ay, int reg);

// Generate sound up to time now.
void ay8910_run(Ay8910 *ay, uint64_t now);

// Start or stop generating samples (from time now). While stopped, the
// registers still work but no sound piles up.
void ay8910_set_rendering(Ay8910 *ay, bool on, uint64_t now);

// Take the samples generated so far (mono, -1..1). Returns how many; the
// pointer stays valid until the next call to any ay8910 function.
int ay8910_take_samples(Ay8910 *ay, const float **samples);

#endif
