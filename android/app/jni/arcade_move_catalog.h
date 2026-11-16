/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "arcade_move_policy.h"
#include "arcade_euro_policy.h"
#include <string.h>

/* A ROM alias can point to another ROM's data without duplicating its arrays. */
typedef struct {
    const char *game;
    const ArcadeRomRule *rules;
    const uint16_t *rule_order[2];
    size_t rule_count[2];
    const ArcadeCostRule *cost_rules;
} ArcadeCineProfile;

#define ARCADE_COUNT(a) (sizeof(a)/sizeof(*(a)))
typedef struct {
    const char *game;
    const ArcadeEuroRule *rules;
    const uint16_t *order[2];
    size_t count[2];
    bool per_player_difficulty;
} ArcadeEuroProfile;
#define ARCADE_EURO_PROFILE(game, data, per_player) {game,data##_rules, \
    {data##_rules_max,data##_rules_fewest}, \
    {ARCADE_COUNT(data##_rules_max),ARCADE_COUNT(data##_rules_fewest)},per_player}

static inline const ArcadeEuroProfile *arcade_euro_profile(
        const ArcadeEuroProfile *profiles,size_t count,const char *game) {
    if(game)for(size_t i=0;i<count;++i)if(!strcmp(profiles[i].game,game))return profiles+i;
    return NULL;
}
#define ARCADE_CINE_PROFILE(game, data) {game,data##_rules, \
    {data##_rules_max,data##_rules_fewest}, \
    {ARCADE_COUNT(data##_rules_max),ARCADE_COUNT(data##_rules_fewest)},NULL}
#define ARCADE_COST_PROFILE(game, data) {game,NULL, \
    {data##_rules_max,data##_rules_fewest}, \
    {ARCADE_COUNT(data##_rules_max),ARCADE_COUNT(data##_rules_fewest)},data##_rules}

static inline const ArcadeCineProfile *arcade_cine_profile(
        const ArcadeCineProfile *profiles,size_t count,const char *game) {
    for(size_t i=0;i<count;++i)if(!strcmp(profiles[i].game,game))return profiles+i;
    return NULL;
}

static inline ArcadeMoveSelection arcade_select_profile(const ArcadeCineProfile *profile,
        unsigned strategy,const uint8_t *ram) {
    ArcadeMoveSelection empty={0,false,0};
    if(!profile || strategy>1)return empty;
    if(profile->cost_rules)return arcade_select_cost_move(profile->cost_rules,
        profile->rule_order[strategy],profile->rule_count[strategy],ram);
    return arcade_select_rom_move(profile->rules,profile->rule_order[strategy],profile->rule_count[strategy],ram);
}
