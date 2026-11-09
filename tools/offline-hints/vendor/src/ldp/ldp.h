// ldp.h - a simple model of a laserdisc player.
//
// A laserdisc game doesn't play its video directly. The game's CPU sends
// commands to a laserdisc player, much like pressing buttons on a remote:
// "search to frame 1366", "play", "pause". The player does the work and
// reports back what it's doing (for example, "still searching").
//
// This module is that player, minus the video. It only tracks state: which
// frame the laser is on, and whether the disc is playing, paused, searching
// or stopped. Whoever owns the player calls ldp_update() as time passes and
// then shows the picture for ldp->frame. Keeping it separate from video and
// input means the same player can be driven from the keyboard now and from
// the game's Z80 later.
//
// The model loosely follows the Pioneer LD-V1000 used by Dragon's Lair:
// a search ends with the player paused on the target frame, and play
// resumes only when told to.

#ifndef LV_LDP_H
#define LV_LDP_H

#include <stdbool.h>

typedef enum {
    LDP_STOPPED,    // disc not spinning; no picture
    LDP_PAUSED,     // holding a still frame
    LDP_PLAYING,    // advancing one frame every 1/fps seconds
    LDP_SEARCHING,  // moving the laser to a new frame
} LdpState;

typedef struct {
    LdpState state;
    int frame;              // current frame number
    double fps;             // frames per second while playing
    double speed;           // times normal speed while playing (1 but for an LD-V1000's FORWARD x1/4 to x5)
    bool blank_during_search;  // show black while searching (as the LD-V1000 does)

    double frame_clock;     // time since the frame last advanced
    double search_clock;    // time left until the search finishes
    int search_target;
} Ldp;

// Start paused on first_frame.
void ldp_init(Ldp *ldp, double fps, int first_frame);

// Commands, as a game (or a person with a remote) would send them.
void ldp_play(Ldp *ldp);
void ldp_pause(Ldp *ldp);
void ldp_stop(Ldp *ldp);
void ldp_search(Ldp *ldp, int frame);
void ldp_step(Ldp *ldp, int delta);  // pause, then move delta frames
void ldp_set_speed(Ldp *ldp, double speed);  // play on at this many times normal speed

// Advance time by the given number of seconds.
void ldp_update(Ldp *ldp, double seconds);

// Is there a picture to show? Not while stopped, nor while searching if
// blank_during_search is set; otherwise a search keeps showing the last frame.
bool ldp_has_picture(const Ldp *ldp);

// How long a search from one frame to another takes, in seconds.
double ldp_search_time(int from, int to);

const char *ldp_state_name(LdpState state);

#endif
