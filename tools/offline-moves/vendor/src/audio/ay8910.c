#include "audio/ay8910.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

// Output level for each volume setting. The chip's volume steps are
// logarithmic, about 3 dB apart (each step is 1/sqrt(2) of the next), with
// 0 meaning silent.
static float volume_level(int v)
{
    return v == 0 ? 0.0f : powf(2.0f, (v - 15) / 2.0f);
}

// How loud the chip is compared with the laserdisc soundtrack (MAME mixes it
// at about a third).
#define CHIP_GAIN 0.33f

void ay8910_init(Ay8910 *ay, double cpu_hz, double chip_hz, double sample_rate)
{
    *ay = (Ay8910){
        .ticks_per_cycle = chip_hz / 8 / cpu_hz,
        .samples_per_tick = sample_rate / (chip_hz / 8),
        .noise_shift = 1,
        .envelope_holding = true,
    };
    ay->regs[7] = 0xFF;  // everything off
}

void ay8910_free(Ay8910 *ay)
{
    free(ay->samples);
    ay->samples = NULL;
}

static uint16_t tone_period(const Ay8910 *ay, int ch)
{
    uint16_t p = (uint16_t)(ay->regs[ch * 2] | ((ay->regs[ch * 2 + 1] & 0x0F) << 8));
    return p ? p : 1;
}

// The current envelope volume, 0-15.
static int envelope_level(const Ay8910 *ay)
{
    if (ay->envelope_holding) return ay->envelope_hold_level;
    return ay->envelope_rising ? ay->envelope_step : 15 - ay->envelope_step;
}

// Advance the envelope one step. Its shape (R13) has four bits:
//   CONTINUE (8), ATTACK (4: start rising), ALTERNATE (2), HOLD (1).
static void envelope_tick(Ay8910 *ay)
{
    if (ay->envelope_holding || ++ay->envelope_step < 16) return;

    uint8_t shape = ay->regs[13];
    int final = ay->envelope_rising ? 15 : 0;
    if (!(shape & 8)) {  // one ramp, then silence
        ay->envelope_holding = true;
        ay->envelope_hold_level = 0;
    } else if (shape & 1) {  // one ramp, then hold (flipped if ALTERNATE)
        ay->envelope_holding = true;
        ay->envelope_hold_level = (uint8_t)((shape & 2) ? 15 - final : final);
    } else {  // repeat, reversing direction each time if ALTERNATE
        ay->envelope_step = 0;
        if (shape & 2) ay->envelope_rising = !ay->envelope_rising;
    }
}

// The chip's output right now. A channel sounds when its tone (if enabled)
// and noise (if enabled) are both high; a disabled source counts as always
// high, so a channel with both off outputs a steady level.
static float mixer_output(const Ay8910 *ay)
{
    bool noise_high = ay->noise_shift & 1;
    float out = 0;
    for (int ch = 0; ch < 3; ch++) {
        bool tone_on = !(ay->regs[7] & (1 << ch));
        bool noise_on = !(ay->regs[7] & (8 << ch));
        bool high = (!tone_on || ay->tone_high[ch]) && (!noise_on || noise_high);
        if (!high) continue;
        uint8_t amp = ay->regs[8 + ch];
        out += volume_level((amp & 0x10) ? envelope_level(ay) : amp & 0x0F);
    }
    return out / 3;
}

// One chip tick (clock / 8): advance the generators, return the mixed output.
static float chip_tick(Ay8910 *ay)
{
    for (int ch = 0; ch < 3; ch++) {
        if (++ay->tone_count[ch] >= tone_period(ay, ch)) {
            ay->tone_count[ch] = 0;
            ay->tone_high[ch] = !ay->tone_high[ch];
        }
    }

    ay->half_tick = !ay->half_tick;
    if (ay->half_tick) {
        uint8_t noise_period = ay->regs[6] & 0x1F;
        if (++ay->noise_count >= (noise_period ? noise_period : 1)) {
            ay->noise_count = 0;
            // 17-bit shift register; the new bit is bit 0 xor bit 3.
            uint32_t bit = (ay->noise_shift ^ (ay->noise_shift >> 3)) & 1;
            ay->noise_shift = (ay->noise_shift >> 1) | (bit << 16);
        }
        uint16_t env_period = (uint16_t)(ay->regs[11] | (ay->regs[12] << 8));
        if (++ay->envelope_count >= (env_period ? env_period : 1)) {
            ay->envelope_count = 0;
            envelope_tick(ay);
        }
    }

    return mixer_output(ay);
}

static void emit_sample(Ay8910 *ay, float level)
{
    // The chip's output never goes negative; a capacitor on the real board
    // removes that steady offset. This filter does the same.
    float out = level - ay->dc_in + 0.995f * ay->dc_out;
    ay->dc_in = level;
    ay->dc_out = out;

    if (ay->sample_count == ay->sample_capacity) {
        ay->sample_capacity = ay->sample_capacity ? ay->sample_capacity * 2 : 4096;
        ay->samples = realloc(ay->samples, (size_t)ay->sample_capacity * sizeof(float));
    }
    ay->samples[ay->sample_count++] = out * CHIP_GAIN;
}

void ay8910_run(Ay8910 *ay, uint64_t now)
{
    if (now <= ay->time) return;
    double ticks = (double)(now - ay->time) * ay->ticks_per_cycle + ay->tick_carry;
    ay->time = now;
    long whole = (long)ticks;
    ay->tick_carry = ticks - (double)whole;

    if (!ay->rendering) {
        // Nobody's listening, so skip making sound. But the envelope keeps
        // running on the real chip, and where it's got to will be heard
        // later, so step it along (it moves once per envelope period).
        uint16_t period = (uint16_t)(ay->regs[11] | (ay->regs[12] << 8));
        if (!period) period = 1;
        long half_ticks = whole / 2;
        long steps = (ay->envelope_count + half_ticks) / period;
        ay->envelope_count = (uint16_t)((ay->envelope_count + half_ticks) % period);
        // A repeating envelope cycles every 32 steps at most; no need to
        // replay thousands of cycles.
        if (steps > 64) steps = 32 + steps % 32;
        for (long i = 0; i < steps && !ay->envelope_holding; i++) envelope_tick(ay);
        return;
    }

    for (long i = 0; i < whole; i++) {
        float level = chip_tick(ay);
        // Average the chip's output over each output sample's span.
        ay->mix_sum += level;
        ay->mix_count++;
        ay->sample_phase += ay->samples_per_tick;
        if (ay->sample_phase >= 1.0) {
            ay->sample_phase -= 1.0;
            emit_sample(ay, (float)(ay->mix_sum / ay->mix_count));
            ay->mix_sum = 0;
            ay->mix_count = 0;
        }
    }
}

void ay8910_write(Ay8910 *ay, uint64_t now, int reg, uint8_t value)
{
    ay8910_run(ay, now);  // the old setting sounds right up to this moment
    reg &= 15;
    ay->regs[reg] = value;
    if (reg == 13) {  // a new envelope shape restarts the envelope
        ay->envelope_step = 0;
        ay->envelope_count = 0;
        ay->envelope_rising = value & 4;
        ay->envelope_holding = false;
    }
}

uint8_t ay8910_read(const Ay8910 *ay, int reg)
{
    return ay->regs[reg & 15];
}

void ay8910_set_rendering(Ay8910 *ay, bool on, uint64_t now)
{
    ay8910_run(ay, now);
    ay->rendering = on;
    ay->sample_count = 0;
    // Start the DC filter from the chip's present output, so switching on
    // doesn't make a click.
    ay->dc_in = mixer_output(ay);
    ay->dc_out = 0;
}

int ay8910_take_samples(Ay8910 *ay, const float **samples)
{
    int n = ay->sample_count;
    *samples = ay->samples;
    ay->sample_count = 0;
    return n;
}
