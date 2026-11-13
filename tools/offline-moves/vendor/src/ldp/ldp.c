#include "ldp/ldp.h"

// How a search moves the laser (following MAME's LD-V1000 model): once per
// video field (1/59.94 s) the player reads where it is and jumps half the
// remaining distance; when within two frames, it lets the disc play up to
// the target, one frame per two fields. So the time grows with the logarithm
// of the distance: about 0.2 s for 1,000 frames, 0.3 s across the whole disc.
#define FIELD_SECONDS (1001.0 / 60000)

double ldp_search_time(int from, int to)
{
    int fields = 0, pos = from;
    while (pos != to) {
        int remaining = to - pos;
        if (remaining > 0 && remaining <= 2) {
            pos += 1;  // creep up on it
            fields += 2;
            continue;
        }
        if (remaining > 0) pos += remaining / 2 > 1 ? remaining / 2 : 1;
        else pos += remaining / 2 < -2 ? remaining / 2 : -2;
        fields++;
    }
    return fields * FIELD_SECONDS;
}

void ldp_init(Ldp *ldp, double fps, int first_frame)
{
    *ldp = (Ldp){
        .state = LDP_PAUSED,
        .frame = first_frame,
        .fps = fps,
        .speed = 1,
    };
}

void ldp_play(Ldp *ldp)
{
    if (ldp->state == LDP_SEARCHING) return;  // busy; a real player ignores it
    if (ldp->state != LDP_PLAYING) ldp->frame_clock = 0;
    ldp->state = LDP_PLAYING;
    ldp->speed = 1;
}

void ldp_set_speed(Ldp *ldp, double speed)
{
    if (ldp->state == LDP_SEARCHING) return;
    if (ldp->state != LDP_PLAYING) ldp->frame_clock = 0;
    ldp->state = LDP_PLAYING;
    ldp->speed = speed;
}

void ldp_pause(Ldp *ldp)
{
    if (ldp->state == LDP_PLAYING) ldp->state = LDP_PAUSED;
}

void ldp_stop(Ldp *ldp)
{
    ldp->state = LDP_STOPPED;
}

void ldp_search(Ldp *ldp, int frame)
{
    if (frame < 0) frame = 0;
    // A search that starts mid-search carries on from where the laser is
    // heading; near enough, from its target.
    int from = ldp->state == LDP_SEARCHING ? ldp->search_target : ldp->frame;
    ldp->state = LDP_SEARCHING;
    ldp->search_target = frame;
    ldp->search_clock = ldp_search_time(from, frame);
}

void ldp_step(Ldp *ldp, int delta)
{
    if (ldp->state == LDP_STOPPED || ldp->state == LDP_SEARCHING) return;
    ldp->state = LDP_PAUSED;
    ldp->frame += delta;
    if (ldp->frame < 0) ldp->frame = 0;
}

void ldp_update(Ldp *ldp, double seconds)
{
    switch (ldp->state) {
    case LDP_PLAYING: {
        // Advance one frame per 1/fps seconds (at normal speed). Keeping
        // the leftover time (instead of resetting the clock each frame)
        // keeps playback at the right speed even though updates don't line
        // up with frames.
        double frame_time = 1.0 / (ldp->fps * ldp->speed);
        ldp->frame_clock += seconds;
        while (ldp->frame_clock >= frame_time) {
            ldp->frame_clock -= frame_time;
            ldp->frame++;
        }
        break;
    }
    case LDP_SEARCHING:
        ldp->search_clock -= seconds;
        if (ldp->search_clock <= 0) {
            ldp->frame = ldp->search_target;
            ldp->state = LDP_PAUSED;  // a search ends on a still frame
        }
        break;
    case LDP_PAUSED:
    case LDP_STOPPED:
        break;
    }
}

bool ldp_has_picture(const Ldp *ldp)
{
    if (ldp->state == LDP_SEARCHING) return !ldp->blank_during_search;
    return ldp->state != LDP_STOPPED;
}

const char *ldp_state_name(LdpState state)
{
    switch (state) {
    case LDP_STOPPED:   return "stopped";
    case LDP_PAUSED:    return "paused";
    case LDP_PLAYING:   return "playing";
    case LDP_SEARCHING: return "searching";
    }
    return "?";
}
