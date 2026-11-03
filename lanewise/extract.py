"""Turn one match-v5 match + timeline into the player's per-game numbers and map positions."""
import math

MAP_SIZE = 14870.0
PINGS = ["allInPings", "assistMePings", "basicPings", "commandPings", "dangerPings", "enemyMissingPings",
         "enemyVisionPings", "getBackPings", "holdPings", "needVisionPings", "onMyWayPings", "pushPings",
         "retreatPings", "visionClearedPings"]
BOX = ["kills", "deaths", "assists", "goldEarned", "totalMinionsKilled", "neutralMinionsKilled",
       "totalDamageDealtToChampions", "damageDealtToTurrets", "damageDealtToEpicMonsters", "visionScore",
       "wardsPlaced", "wardsKilled", "totalHealsOnTeammates", "totalDamageShieldedOnTeammates",
       "timeCCingOthers", "champLevel"]
CHALLENGES = ["teamDamagePercentage", "killParticipation", "enemyJungleMonsterKills", "soloKills"]


def lane_of(role):
    return {"TOP": "top", "MIDDLE": "mid", "BOTTOM": "bot", "UTILITY": "bot"}.get(role)


def zone(x, y, team):
    """Coarse zone from the team's own perspective (blue side = bottom-left)."""
    if team == 200:
        x, y = MAP_SIZE - x, MAP_SIZE - y
    d = (x + y) / MAP_SIZE
    half = "enemy" if d > 1.08 else "own" if d < 0.92 else "river"
    if x < 3000 and y < 3000:
        return "own_base"
    if x > MAP_SIZE - 3000 and y > MAP_SIZE - 3000:
        return "enemy_base"
    if (x < 2600 and y > 5000) or (y > MAP_SIZE - 2600 and x < MAP_SIZE - 5000):
        return f"{half}_top"
    if (y < 2600 and x > 5000) or (x > MAP_SIZE - 2600 and y < MAP_SIZE - 5000):
        return f"{half}_bot"
    if abs(x - y) < 1700:
        return f"{half}_mid"
    return f"{half}_jungle"


def player_game(match, timeline, puuid):
    """Per-game row for `puuid`, or None for remakes / other queues."""
    info = match["info"]
    parts = info["participants"]
    me = next((p for p in parts if p["puuid"] == puuid), None)
    if me is None or info.get("gameDuration", 0) < 300:
        return None
    pid, team, role = me["participantId"], me["teamId"], me.get("teamPosition") or ""
    minutes = info["gameDuration"] / 60.0
    opp = next((p for p in parts if p["teamId"] != team and (p.get("teamPosition") or "") == role and role), None)
    ch = me.get("challenges") or {}
    r = {
        "match_id": match["metadata"]["matchId"], "queue": info.get("queueId"),
        "game_start": (info.get("gameStartTimestamp") or info.get("gameCreation", 0)) / 1000.0,
        "game_end": (info.get("gameEndTimestamp") or 0) / 1000.0, "minutes": minutes,
        "patch": ".".join(info.get("gameVersion", "").split(".")[:2]),
        "win": bool(me["win"]), "team": team, "role": role, "champion_id": me["championId"],
        "champion": me["championName"], "opp_champion": opp["championName"] if opp else None,
        "opp_champion_id": opp["championId"] if opp else None,
        "remake_or_ff15": info["gameDuration"] < 900, "early_surrender": bool(me.get("gameEndedInEarlySurrender")),
        "surrender": bool(me.get("gameEndedInSurrender")), "afk": bool(me.get("wasAfk")),
        "team_gold": sum(p["goldEarned"] for p in parts if p["teamId"] == team),
        "items": [me.get(f"item{i}", 0) for i in range(7)],
        "summoners": [me.get("summoner1Id"), me.get("summoner2Id")],
        "keystone": ((me.get("perks") or {}).get("styles") or [{}])[0].get("selections", [{}])[0].get("perk"),
    }
    for k in BOX:
        r[k] = me.get(k, 0)
    for k in CHALLENGES:
        r["c_" + k] = float(ch.get(k) or 0.0)
    r["pings"] = sum(me.get(k, 0) for k in PINGS)

    # ------------------------------------------------------------- timeline
    frames = (timeline or {}).get("info", {}).get("frames", [])
    team_of = {p["participantId"]: p["teamId"] for p in parts}
    opp_id = opp["participantId"] if opp else None
    positions, kills_at, deaths_at = [], [], []
    for m in (10, 15):
        f = frames[m] if len(frames) > m else None
        mine = f["participantFrames"].get(str(pid)) if f else None
        theirs = f["participantFrames"].get(str(opp_id)) if (f and opp_id) else None
        cs = (mine["minionsKilled"] + mine["jungleMinionsKilled"]) if mine else None
        r[f"cs{m}"] = cs
        for k, key in (("gold", "totalGold"), ("xp", "xp")):
            r[f"{k}{m}_diff"] = (mine[key] - theirs[key]) if (mine and theirs) else None
        r[f"cs{m}_diff"] = (cs - theirs["minionsKilled"] - theirs["jungleMinionsKilled"]) if (mine and theirs) else None
    for i, f in enumerate(frames[1:], start=1):
        pf = f["participantFrames"].get(str(pid))
        if pf and pf.get("position"):
            positions.append((i, pf["position"]["x"], pf["position"]["y"]))

    ev = [e for f in frames for e in f.get("events", [])]
    kills = [e for e in ev if e["type"] == "CHAMPION_KILL"]
    fights, cur = [], None
    for e in kills:
        pos = e.get("position", {"x": 0, "y": 0})
        if cur and e["timestamp"] - cur["t1"] < 20000 and math.dist((pos["x"], pos["y"]), cur["pos"]) < 2500:
            cur["ev"].append(e)
            cur["t1"], cur["pos"] = e["timestamp"], (pos["x"], pos["y"])
        else:
            cur = {"t1": e["timestamp"], "pos": (pos["x"], pos["y"]), "ev": [e]}
            fights.append(cur)
    c = dict(deaths_pre14=0, deaths_enemy_half=0, takedowns_pre14=0, roam_takedowns=0, first_death=None,
             obj_team=0, obj_present=0, wards_control=0, teamfights=0, teamfights_team=0, skirmishes=0)
    for e in kills:
        t = e["timestamp"] / 60000.0
        pos = e.get("position", {"x": 0, "y": 0})
        z = zone(pos["x"], pos["y"], team)
        if e.get("victimId") == pid:
            deaths_at.append((round(t, 1), pos["x"], pos["y"]))
            c["first_death"] = c["first_death"] if c["first_death"] is not None else t
            c["deaths_pre14"] += t < 14
            c["deaths_enemy_half"] += z.startswith("enemy")
        if pid == e.get("killerId") or pid in (e.get("assistingParticipantIds") or []):
            kills_at.append((round(t, 1), pos["x"], pos["y"], pid == e.get("killerId")))
            if t < 14:
                c["takedowns_pre14"] += 1
                lane = lane_of(role)
                if lane and not z.endswith(lane) and not z.endswith("base"):
                    c["roam_takedowns"] += 1
    for e in ev:
        if e["type"] == "ELITE_MONSTER_KILL" and e.get("killerTeamId") == team:
            c["obj_team"] += 1
            c["obj_present"] += pid in ({e.get("killerId")} | set(e.get("assistingParticipantIds") or []))
        elif e["type"] == "WARD_PLACED" and e.get("creatorId") == pid and e.get("wardType") == "CONTROL_WARD":
            c["wards_control"] += 1
    for f in fights:
        who = set()
        for e in f["ev"]:
            who |= {e.get("victimId"), e.get("killerId"), *(e.get("assistingParticipantIds") or [])}
        who -= {0, None}
        if team not in {team_of.get(w) for w in who}:
            continue
        if len(who) >= 6:
            c["teamfights_team"] += 1
            c["teamfights"] += pid in who
        elif pid in who:
            c["skirmishes"] += 1
    r.update(c)
    r["first_death_min"] = min(c["first_death"] if c["first_death"] is not None else minutes, 25.0)
    r["has_timeline"] = bool(frames)
    r["positions"] = positions
    r["kills_at"] = kills_at
    r["deaths_at"] = deaths_at
    return r
