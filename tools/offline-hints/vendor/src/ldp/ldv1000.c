#include "ldp/ldv1000.h"

#include <math.h>
#include <stddef.h>

// Command bytes.
enum {
    CMD_CLEAR = 0xBF,
    CMD_PLAY = 0xFD,
    CMD_STOP = 0xFB,
    CMD_AUTOSTOP = 0xF3,
    CMD_SEARCH = 0xF7,
    CMD_STEP_FWD = 0xF6,
    CMD_STEP_REV = 0xFE,
    CMD_REJECT = 0xF9,
    CMD_NO_ENTRY = 0xFF,
    CMD_AUDIO1 = 0xF4,
    CMD_AUDIO2 = 0xFC,
    CMD_GET_FRAME = 0xC2,
    CMD_FORWARD_X0 = 0xA0,  // A0-A7: play forward at a set speed (0, 1/4, 1/2, 1, 2, 3, 4, 5)
    CMD_FORWARD_X5 = 0xA7,
    CMD_SKIP_10 = 0xB1,  // B1-BA: skip forward 10, 20, ... 100 frames
    CMD_SKIP_100 = 0xBA,
};

// After GET FRAME NUMBER, the status byte carries the frame number's five
// digits instead, most significant first, one per field, starting at the
// next field's status. Each is the digit's character code, '0' to '9' (30
// to 39). (Found by reading how the games read the reply: Super Don
// Quix-ote sends the NO ENTRY that follows the command in the next field,
// and takes the first digit from the status read in that same exchange,
// keeping the low four bits; Astron Belt subtracts 30 from each byte.)
#define FRAME_REPLY_DIGITS 5
#define FRAME_REPLY_DELAY 1  // fields

static int64_t field_number(const Ldv1000 *ld, uint64_t now);

// Status bytes. READY (bit 7) is or'ed in when the player will take a
// command; SEARCH_FINISH has it built in.
enum {
    STATUS_READY = 0x80,
    STATUS_PARK = 0x7C,
    STATUS_PLAY = 0x64,
    STATUS_STOP = 0x65,
    STATUS_SEARCH = 0x50,
    STATUS_SEARCH_FINISH = 0xD0,
    STATUS_AUTOSTOP = 0x54,
    STATUS_FORWARD = 0x2E,  // playing at a set speed (FORWARD x1/4 to x5)
};

// Digits are sent as these bytes, in order 0 to 9.
static const uint8_t digit_bytes[10] = {0x3F, 0x0F, 0x8F, 0x4F, 0x2F, 0xAF, 0x6F, 0x1F, 0x9F, 0x5F};

static int digit_value(uint8_t byte)
{
    for (int i = 0; i < 10; i++)
        if (digit_bytes[i] == byte) return i;
    return -1;
}

// The number entered so far, as a plain integer.
static int entered_number(const Ldv1000 *ld)
{
    int n = 0;
    for (int i = 0; i < ld->digit_count; i++) n = n * 10 + ld->digits[i];
    return n;
}

void ldv1000_init(Ldv1000 *ld, Ldp *ldp, double clock_hz)
{
    *ld = (Ldv1000){
        .ldp = ldp,
        .clock_hz = clock_hz,
        .status = STATUS_PARK | STATUS_READY,
        .autostop_frame = -1,
        .reply_field = -1,
        .audio = {true, true},
    };
    ldp->frame = 0;
    ldp->blank_during_search = true;  // the LD-V1000 outputs no picture mid-search
    ldp_stop(ldp);  // parked: disc not spinning
    ld->previous_state = ldp->state;
}

void ldv1000_update(Ldv1000 *ld, uint64_t now)
{
    if (now <= ld->last) return;
    Ldp *ldp = ld->ldp;
    ldp_update(ldp, (double)(now - ld->last) / ld->clock_hz);
    ld->last = now;

    // A search that just finished leaves the player paused on the target,
    // ready for the next command.
    if (ld->previous_state == LDP_SEARCHING && ldp->state == LDP_PAUSED)
        ld->status = STATUS_SEARCH_FINISH;

    // AUTOSTOP: play until the target frame, then hold it.
    if (ld->autostop_frame >= 0 && ldp->state == LDP_PLAYING && ldp->frame >= ld->autostop_frame) {
        ldp_pause(ldp);
        ldp->frame = ld->autostop_frame;
        ld->autostop_frame = -1;
        ld->status = (uint8_t)((ld->status & STATUS_READY) | STATUS_STOP);
    }

    // A timed STOP (STOP with a number) resumes playing when time's up.
    if (ld->resume_at && now >= ld->resume_at) {
        ld->resume_at = 0;
        ldp_play(ldp);
        ld->status = ld->status_before_stop;
    }

    ld->previous_state = ldp->state;
}

static void execute(Ldv1000 *ld, uint64_t now, uint8_t byte)
{
    Ldp *ldp = ld->ldp;
    int number = entered_number(ld);

    switch (byte) {
    case CMD_PLAY:
        if (ldp->state == LDP_SEARCHING) {  // finish the search instantly
            ldp->frame = ldp->search_target;
            ldp->state = LDP_PAUSED;
        }
        ldp_play(ldp);
        ld->autostop_frame = -1;
        ld->muted = false;
        ld->status = STATUS_PLAY;
        break;
    case CMD_STOP:
        if (ld->digit_count > 0) {  // hold for number * 0.1 s, then play on
            ld->resume_at = now + (uint64_t)(number * 0.1 * ld->clock_hz);
            ld->status_before_stop = ld->status;
        }
        ldp_pause(ldp);
        ld->status = STATUS_STOP;
        break;
    case CMD_SEARCH:
        ldp_search(ldp, number);
        ld->autostop_frame = -1;
        ld->status = STATUS_SEARCH;
        break;
    case CMD_AUTOSTOP:
        if (number < ldp->frame) {  // a target behind us becomes a search
            ldp_search(ldp, number);
            ld->status = STATUS_SEARCH;
        } else {
            ld->autostop_frame = number;
            ld->muted = false;
            ldp_play(ldp);
            ld->status = STATUS_AUTOSTOP;
        }
        break;
    case CMD_STEP_FWD:
    case CMD_STEP_REV:
        ldp_step(ldp, byte == CMD_STEP_FWD ? 1 : -1);
        ld->status = STATUS_STOP;
        break;
    case CMD_REJECT:  // stop the disc and park
        ldp_stop(ldp);
        ld->autostop_frame = -1;
        ld->status = STATUS_PARK;
        break;
    case CMD_AUDIO1:
    case CMD_AUDIO2: {
        // With no number, toggle the channel; with a number, set it on/off.
        int ch = byte == CMD_AUDIO1 ? 0 : 1;
        ld->audio[ch] = ld->digit_count ? (number & 1) : !ld->audio[ch];
        break;
    }
    case CMD_GET_FRAME:
        ld->reply_frame = ldp->frame;
        ld->reply_field = field_number(ld, now) + FRAME_REPLY_DELAY;
        break;
    default:
        if (byte == CMD_FORWARD_X0) {  // speed 0: hold the picture
            ldp_pause(ldp);
            ld->status = STATUS_STOP;
        } else if (byte > CMD_FORWARD_X0 && byte <= CMD_FORWARD_X5) {
            // Forward at 1/4 to 5 times normal speed. (GP World plays the
            // disc at the car's speed, switching between two of these to
            // get the speeds in between.)
            //
            // Started from a standstill, this plays without sound; sent
            // while the disc is already playing, the sound stays on. (Super
            // Don Quix-ote's "demo sounds" switch depends on it: after each
            // search in the attract mode, it sends PLAY then FORWARD x1 for
            // sound, or STOP then FORWARD x1 for silence.)
            static const double speeds[8] = {0, 0.25, 0.5, 1, 2, 3, 4, 5};
            if (ldp->state != LDP_PLAYING) ld->muted = true;
            ldp_set_speed(ldp, speeds[byte - CMD_FORWARD_X0]);
            ld->autostop_frame = -1;
            ld->status = STATUS_FORWARD;
        } else if (byte >= CMD_SKIP_10 && byte <= CMD_SKIP_100) {
            // Jump ahead and carry on as before. The player can move the
            // laser this far during one vertical blank, so the picture
            // doesn't break up. (Super Don Quix-ote skips the capture scene
            // that follows each arrow when you answer it in time.)
            ldp->frame += 10 * (byte - CMD_SKIP_10 + 1);
        }
        // CLEAR, display and other commands: nothing to do
        break;
    }
}

void ldv1000_write(Ldv1000 *ld, uint64_t now, uint8_t byte)
{
    ldv1000_update(ld, now);

    // NO ENTRY just makes the player ready for the next byte. It isn't a
    // command, so it doesn't end a number being entered (games may send it
    // more than once between digits).
    if (byte == CMD_NO_ENTRY) {
        ld->status |= STATUS_READY;
        return;
    }
    if (!(ld->status & STATUS_READY)) return;  // busy with the last command
    ld->status &= ~STATUS_READY;

    uint8_t previous = ld->last_command;
    ld->last_command = byte;
    int digit = digit_value(byte);
    if (digit >= 0) {
        if (ld->digit_count < (int)sizeof ld->digits) ld->digits[ld->digit_count++] = (uint8_t)digit;
        if (ld->konami_rom) ld->status |= STATUS_READY;
        return;
    }
    if (ld->konami_rom && previous == 0x20 && byte == 0x31) {
        // Konami's skip back, for the moments that loop (the twirling axe,
        // the bats' red eyes): like SKIP FORWARD, a jump the player makes
        // within a vertical blank.
        ld->ldp->frame = ld->ldp->frame > 16 ? ld->ldp->frame - 16 : 0;
    }
    execute(ld, now, byte);
    ld->digit_count = 0;  // any non-digit ends the number
    ld->previous_state = ld->ldp->state;
}

uint8_t ldv1000_read_status(Ldv1000 *ld, uint64_t now)
{
    ldv1000_update(ld, now);
    if (ld->reply_field >= 0) {  // answering GET FRAME NUMBER
        int64_t i = field_number(ld, now) - ld->reply_field;
        if (i >= FRAME_REPLY_DIGITS) {
            ld->reply_field = -1;
        } else if (i >= 0) {
            int digit = ld->reply_frame;
            for (int64_t k = i; k < FRAME_REPLY_DIGITS - 1; k++) digit /= 10;
            return (uint8_t)('0' + digit % 10);
        }
    }
    return ld->status;
}

bool ldv1000_audio_on(const Ldv1000 *ld, int channel)
{
    return ld->audio[channel] && !ld->muted;
}

// ---------------------------------------------------------------------------
// Strobes
// ---------------------------------------------------------------------------
//
// Times in microseconds, from MAME's model. The status strobe is active for
// 26 us; the command strobe starts 54 us after it and lasts 25 us. Parked,
// they repeat every 21 ms from time zero; otherwise once per field, starting
// 500 us into it.

#define PARKED_PERIOD_US 21000.0
#define FIELD_PERIOD_US (1e6 / 59.94)
#define FIELD_STROBE_OFFSET_US 500.0
#define STATUS_STROBE_US 26.0
#define COMMAND_STROBE_START_US 54.0
#define COMMAND_STROBE_US 25.0

// Microseconds since the last status strobe started (can be negative just
// before the first one in a field).
static double since_status_strobe(Ldv1000 *ld, uint64_t now)
{
    ldv1000_update(ld, now);
    double us = (double)now * 1e6 / ld->clock_hz;
    if (ld->ldp->state == LDP_STOPPED) return fmod(us, PARKED_PERIOD_US);
    return fmod(us, FIELD_PERIOD_US) - FIELD_STROBE_OFFSET_US;
}

// Which field it is, counting from time zero, changing at each field's
// status strobe. (A microsecond of slack, so a strobe exactly on time
// counts as the new field.)
static int64_t field_number(const Ldv1000 *ld, uint64_t now)
{
    double us = (double)now * 1e6 / ld->clock_hz;
    return (int64_t)floor((us - FIELD_STROBE_OFFSET_US + 1.0) / FIELD_PERIOD_US);
}

bool ldv1000_status_strobe(Ldv1000 *ld, uint64_t now)
{
    double t = since_status_strobe(ld, now);
    return t >= 0 && t < STATUS_STROBE_US;
}

bool ldv1000_command_strobe(Ldv1000 *ld, uint64_t now)
{
    double t = since_status_strobe(ld, now);
    return t >= COMMAND_STROBE_START_US && t < COMMAND_STROBE_START_US + COMMAND_STROBE_US;
}

const char *ldv1000_command_name(uint8_t byte)
{
    static const char *digits[10] = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9"};
    int d = digit_value(byte);
    if (d >= 0) return digits[d];
    switch (byte) {
    case CMD_CLEAR: return "CLEAR";
    case CMD_PLAY: return "PLAY";
    case CMD_STOP: return "STOP";
    case CMD_AUTOSTOP: return "AUTOSTOP";
    case CMD_SEARCH: return "SEARCH";
    case CMD_STEP_FWD: return "STEP FWD";
    case CMD_STEP_REV: return "STEP REV";
    case CMD_REJECT: return "REJECT";
    case CMD_NO_ENTRY: return "NO ENTRY";
    case CMD_AUDIO1: return "AUDIO1";
    case CMD_AUDIO2: return "AUDIO2";
    case 0xF5: return "STORE";
    case 0x7F: return "RECALL";
    case 0xF1: return "DISPLAY";
    case 0xF0: return "SCAN FWD";
    case 0xF8: return "SCAN REV";
    case 0xCC: return "LOAD";
    case 0xCD: return "DISPLAY OFF";
    case 0xCE: return "DISPLAY ON";
    case 0xC2: return "GET FRAME NUMBER";
    case 0xA0: return "FORWARD x0";
    case 0xA1: return "FORWARD x1/4";
    case 0xA2: return "FORWARD x1/2";
    case 0xA3: return "FORWARD x1";
    case 0xA4: return "FORWARD x2";
    case 0xA5: return "FORWARD x3";
    case 0xA6: return "FORWARD x4";
    case 0xA7: return "FORWARD x5";
    case 0xB1: return "SKIP 10";
    case 0xB2: return "SKIP 20";
    case 0xB3: return "SKIP 30";
    case 0xB4: return "SKIP 40";
    case 0xB5: return "SKIP 50";
    case 0xB6: return "SKIP 60";
    case 0xB7: return "SKIP 70";
    case 0xB8: return "SKIP 80";
    case 0xB9: return "SKIP 90";
    case 0xBA: return "SKIP 100";
    default: return NULL;
    }
}
