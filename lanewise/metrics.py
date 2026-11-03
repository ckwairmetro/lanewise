"""Metric definitions shared by the app and the benchmark builder.

Every function takes `r`, which can be a single game (dict) or a whole pandas DataFrame of games,
so the exact same formulas produce both the benchmarks and a player's numbers.
"""

ROLES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
ROLE_NAMES = {"TOP": "Top", "JUNGLE": "Jungle", "MIDDLE": "Mid", "BOTTOM": "Bot", "UTILITY": "Support"}
TIERS = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND", "MASTER+"]


def _pm(col):
    return lambda r: r[col] / r["minutes"]


# name -> (label, function, higher_is_better)
METRICS = {
    "gold10_diff":      ("Gold lead @10", lambda r: r["gold10_diff"], True),
    "xp10_diff":        ("XP lead @10", lambda r: r["xp10_diff"], True),
    "cs10_diff":        ("CS lead @10", lambda r: r["cs10_diff"], True),
    "gold15_diff":      ("Gold lead @15", lambda r: r["gold15_diff"], True),
    "cs_pm":            ("CS per minute", lambda r: (r["totalMinionsKilled"] + r["neutralMinionsKilled"]) / r["minutes"], True),
    "cs10":             ("CS @10", lambda r: r["cs10"], True),
    "dpm":              ("Damage per minute", _pm("totalDamageDealtToChampions"), True),
    "dmg_share":        ("Team damage share", lambda r: r["c_teamDamagePercentage"], True),
    "kp":               ("Kill participation", lambda r: r["c_killParticipation"], True),
    "takedowns_pm":     ("Takedowns per minute", lambda r: (r["kills"] + r["assists"]) / r["minutes"], True),
    "deaths_pm":        ("Deaths per minute", _pm("deaths"), False),
    "deaths_pre14":     ("Deaths before 14:00", lambda r: r["deaths_pre14"], False),
    "first_death_min":  ("First death (minute)", lambda r: r["first_death_min"], True),
    "vision_pm":        ("Vision score per minute", _pm("visionScore"), True),
    "control_wards_pm": ("Control wards per minute", _pm("wards_control"), True),
    "ward_kills_pm":    ("Wards cleared per minute", _pm("wardsKilled"), True),
    "obj_presence":     ("Objective presence", lambda r: r["obj_present"] / (r["obj_team"] + 1), True),
    "turret_dmg_pm":    ("Turret damage per minute", _pm("damageDealtToTurrets"), True),
    "epic_dmg_pm":      ("Epic monster damage per minute", _pm("damageDealtToEpicMonsters"), True),
    "assists_pm":       ("Assists per minute", _pm("assists"), True),
    "heal_shield_pm":   ("Heal & shield on allies per minute",
                         lambda r: (r["totalHealsOnTeammates"] + r["totalDamageShieldedOnTeammates"]) / r["minutes"], True),
    "cc_pm":            ("Crowd control per minute", _pm("timeCCingOthers"), True),
    # style (no better/worse): used for tendencies
    "early_share":      ("Share of takedowns before 14:00", lambda r: r["takedowns_pre14"] / (r["kills"] + r["assists"] + 1), None),
    "roam_takedowns":   ("Takedowns away from own lane before 14:00", lambda r: r["roam_takedowns"], None),
    "enemy_half_deaths": ("Deaths in enemy half per minute", lambda r: r["deaths_enemy_half"] / r["minutes"], None),
    "teamfight_presence": ("Teamfight presence", lambda r: r["teamfights"] / (r["teamfights_team"] + 1), None),
    "skirmish_ratio":   ("Small fights vs teamfights", lambda r: r["skirmishes"] / (r["skirmishes"] + r["teamfights"] + 1), None),
    "gold_share":       ("Team gold share", lambda r: r["goldEarned"] / (r["team_gold"] + 1), None),
    "enemy_jungle":     ("Enemy jungle camps taken", lambda r: r["c_enemyJungleMonsterKills"], None),
    "pings_pm":         ("Pings per minute", lambda r: r["pings"] / r["minutes"], None),
    "wards_pm":         ("Wards placed per minute", _pm("wardsPlaced"), None),
    "solo_kills":       ("Solo kills", lambda r: r["c_soloKills"], None),
}

# Aspects shown to the player: weighted blends of metric percentiles. Role overrides replace the list.
ASPECTS = {
    "Laning":     {"metrics": {"gold10_diff": 1, "xp10_diff": 1, "cs10_diff": 1, "gold15_diff": 1.5},
                   "roles": {"JUNGLE": {"gold15_diff": 1, "xp10_diff": 1, "enemy_jungle": 0}}},
    "Farming":    {"metrics": {"cs_pm": 2, "cs10": 1},
                   "roles": {"UTILITY": {"gold15_diff": 1}}},
    "Fighting":   {"metrics": {"dpm": 1, "dmg_share": 1, "kp": 1, "takedowns_pm": 1}},
    "Survival":   {"metrics": {"deaths_pm": 2, "deaths_pre14": 1, "first_death_min": 1}},
    "Vision":     {"metrics": {"vision_pm": 2, "control_wards_pm": 1, "ward_kills_pm": 1}},
    "Objectives": {"metrics": {"obj_presence": 2, "turret_dmg_pm": 1},
                   "roles": {"JUNGLE": {"obj_presence": 2, "epic_dmg_pm": 1.5, "turret_dmg_pm": 0.5}}},
    "Teamplay":   {"metrics": {"assists_pm": 1, "kp": 1, "cc_pm": 1},
                   "roles": {"UTILITY": {"assists_pm": 1, "kp": 1, "cc_pm": 1, "heal_shield_pm": 1}}},
}

ASPECT_TIPS = {
    "Laning": "Compare your gold and CS at 10 minutes with your opponent's. Look for the trades and recalls that cost you most.",
    "Farming": "Practise last-hitting under tower, and catch side waves between objectives.",
    "Fighting": "Stay in range of your team's fights and make sure your damage lands on champions.",
    "Survival": "Most early deaths come from overextending without vision. Ward before you push past the river.",
    "Vision": "Buy a control ward on every back, and use your sweeper before objectives.",
    "Objectives": "Group 30-45 seconds before dragon, grubs, herald and baron spawn.",
    "Teamplay": "Follow up on your teammates' engages and pick fights where your crowd control lands.",
}

TENDENCIES = {
    "Aggression":       {"early_share": 1, "enemy_half_deaths": 1, "solo_kills": 1},
    "Roaming":          {"roam_takedowns": 1},
    "Teamfight focus":  {"teamfight_presence": 1, "skirmish_ratio": -1},
    "Resource focus":   {"gold_share": 1},
    "Invading":         {"enemy_jungle": 1},
    "Vision habit":     {"wards_pm": 1},
    "Communication":    {"pings_pm": 1},
}

TENDENCY_TEXT = {
    "Aggression": ("You look for fights early and often, and you push into enemy territory.",
                   "You play patiently and rarely force early fights."),
    "Roaming": ("You leave lane to help other lanes before 14 minutes.", "You stay in your lane during the laning phase."),
    "Teamfight focus": ("You group for 5v5s more than small skirmishes.", "You prefer small fights and picks to full teamfights."),
    "Resource focus": ("You take a big share of your team's gold. You play as the carry.",
                       "You leave resources to teammates and play as an enabler."),
    "Invading": ("You take enemy jungle camps regularly.", "You rarely take camps in the enemy jungle."),
    "Vision habit": ("You place more wards than most players in your role.", "You place fewer wards than most players in your role."),
    "Communication": ("You ping a lot to talk to your team.", "You rarely use pings."),
}
