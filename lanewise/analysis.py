"""Build a player's report: aspect percentiles vs similar players, tendencies, traits, sessions,
champion pool review and heatmap data."""
import json
import statistics
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from .extract import player_game
from .metrics import ASPECT_TIPS, ASPECTS, METRICS, ROLE_NAMES, TENDENCIES, TENDENCY_TEXT, TIERS

DATA = Path(__file__).resolve().parent / "data"
BENCH = json.loads((DATA / "benchmarks.json").read_text(encoding="utf-8"))
CHAMPS = json.loads((DATA / "champions.json").read_text(encoding="utf-8"))
QS = np.array(BENCH["quantiles"], dtype=float)
KEY_NAME = {v["key"]: v["name"] for v in CHAMPS.values()}        # "MonkeyKing" -> "Wukong"
named = lambda keys: [{"key": k, "name": KEY_NAME.get(k, k)} for k in keys]
SESSION_GAP = 45 * 60


# ---------------------------------------------------------------- benchmarks
def bench_tier(tier):
    """Benchmark bucket for a rank; apex tiers share one bucket. Falls back to the nearest tier with data."""
    t = "MASTER+" if tier in ("MASTER", "GRANDMASTER", "CHALLENGER") else (tier or "GOLD")
    if t in BENCH["tiers"] and BENCH["tiers"][t]:
        return t
    i = TIERS.index(t) if t in TIERS else 3
    for d in range(1, len(TIERS)):
        for j in (i - d, i + d):
            if 0 <= j < len(TIERS) and BENCH["tiers"].get(TIERS[j]):
                return TIERS[j]
    return next(iter(BENCH["tiers"]))


def percentile(metric, value, tier, role):
    q = BENCH["tiers"].get(tier, {}).get(role, {}).get(metric)
    if q is None or value is None or not np.isfinite(value):
        return None
    return float(np.interp(value, np.array(q), QS))


def bench_median(metric, tier, role):
    q = BENCH["tiers"].get(tier, {}).get(role, {}).get(metric)
    return q[len(q) // 2] if q else None


def champ_offset(metric, role, champion_id):
    return BENCH["champion_offsets"].get(role, {}).get(str(champion_id), {}).get(metric, 0.0)


def aspect_weights(aspect, role):
    spec = ASPECTS[aspect]
    return spec.get("roles", {}).get(role, spec["metrics"])


# ---------------------------------------------------------------- per game scoring
def score_game(g, tier):
    """Percentile of every metric (champion-adjusted for skill metrics) and every aspect for one game."""
    role = g["role"]
    pct, raw = {}, {}
    for m, (_, fn, better) in METRICS.items():
        try:
            v = fn(g)
        except (TypeError, ZeroDivisionError, KeyError):
            v = None
        if v is None:
            continue
        raw[m] = v
        adj = v - champ_offset(m, role, g["champion_id"]) if better is not None else v
        p = percentile(m, adj, tier, role)
        if p is not None:
            pct[m] = p if better in (True, None) else 100 - p
    aspects = {}
    for a in ASPECTS:
        w = {m: x for m, x in aspect_weights(a, role).items() if x and m in pct}
        if w:
            aspects[a] = sum(pct[m] * x for m, x in w.items()) / sum(w.values())
    overall = statistics.fmean(aspects.values()) if aspects else None
    return {"pct": pct, "raw": raw, "aspects": aspects, "overall": overall}


# ---------------------------------------------------------------- report
def fetch_games(riot, platform, puuid, count):
    ids = riot.match_ids(platform, puuid, count=count)

    def one(mid):
        m = riot.match(platform, mid)
        if not m:
            return None
        return player_game(m, riot.timeline(platform, mid), puuid)

    with ThreadPoolExecutor(6) as ex:
        games = [g for g in ex.map(one, ids) if g]
    return sorted(games, key=lambda g: g["game_start"])


def build_report(riot, platform, riot_id, count=20):
    if "#" not in riot_id:
        raise ValueError("Enter your Riot ID as Name#TAG")
    name, tag = riot_id.rsplit("#", 1)
    acct = riot.account(platform, name.strip(), tag.strip())
    if not acct:
        raise LookupError(f"No account named {riot_id}")
    puuid = acct["puuid"]
    league = riot.league(platform, puuid)
    solo = next((e for e in league if e.get("queueType") == "RANKED_SOLO_5x5"), None)
    mastery = riot.mastery(platform, puuid)
    games = fetch_games(riot, platform, puuid, count)
    tier = bench_tier(solo["tier"] if solo else None)

    scored = []
    for g in games:
        s = score_game(g, tier) if not g["remake_or_ff15"] and g["role"] in ROLE_NAMES else None
        scored.append((g, s))
    valid = [(g, s) for g, s in scored if s]
    report = {
        "player": {"riot_id": f"{acct.get('gameName')}#{acct.get('tagLine')}", "platform": platform,
                   "rank": ({"tier": solo["tier"], "division": solo.get("rank"), "lp": solo.get("leaguePoints"),
                             "wins": solo.get("wins"), "losses": solo.get("losses")} if solo else None),
                   "benchmark_tier": tier, "games_analyzed": len(valid), "games_fetched": len(games)},
        "aspects": aspects_summary(valid, tier),
        "tendencies": tendencies(valid),
        "sessions": sessions(scored),
        "champion_pool": champion_pool(valid, mastery),
        "heatmap": [{"match_id": g["match_id"], "team": g["team"], "role": g["role"], "champion": g["champion"],
                     "win": g["win"], "positions": g["positions"], "kills": g["kills_at"], "deaths": g["deaths_at"]}
                    for g in games if g["has_timeline"]],
        "matches": [{"match_id": g["match_id"], "start": g["game_start"], "minutes": round(g["minutes"], 1),
                     "champion": g["champion"], "role": g["role"], "win": g["win"], "k": g["kills"],
                     "d": g["deaths"], "a": g["assists"],
                     "cs": g["totalMinionsKilled"] + g["neutralMinionsKilled"], "opp": g["opp_champion"],
                     "score": round(s["overall"]) if s else None, "patch": g["patch"]} for g, s in reversed(scored)],
    }
    report["traits"] = traits(report, valid)
    return report


def aspects_summary(valid, tier):
    if not valid:
        return {}
    by_aspect = defaultdict(list)
    for _, s in valid:
        for a, v in s["aspects"].items():
            by_aspect[a].append(v)
    roles = Counter(g["role"] for g, _ in valid)
    main_role = roles.most_common(1)[0][0]
    out = {"main_role": main_role, "role_games": dict(roles), "overall": round(statistics.fmean(
        s["overall"] for _, s in valid if s["overall"] is not None)), "aspects": {}}
    for a, vals in by_aspect.items():
        out["aspects"][a] = {"percentile": round(statistics.fmean(vals)), "games": len(vals), "tip": ASPECT_TIPS[a],
                             "details": aspect_details(a, valid, tier, main_role)}
    ranked = sorted(out["aspects"].items(), key=lambda kv: kv[1]["percentile"])
    out["strengths"] = [a for a, v in ranked[::-1][:2] if v["percentile"] >= 55]
    out["focus"] = [a for a, v in ranked[:2] if v["percentile"] <= 45]
    return out


def aspect_details(aspect, valid, tier, main_role):
    """Each metric in the aspect: the player's average vs the median of similar players."""
    rows = []
    for m, w in aspect_weights(aspect, main_role).items():
        if not w:
            continue
        vals = [s["raw"][m] for g, s in valid if g["role"] == main_role and m in s["raw"] and s["raw"][m] is not None]
        pcts = [s["pct"][m] for g, s in valid if g["role"] == main_role and m in s["pct"]]
        if not vals:
            continue
        rows.append({"metric": METRICS[m][0], "you": round(statistics.fmean(vals), 2),
                     "typical": round(bench_median(m, tier, main_role), 2) if bench_median(m, tier, main_role) is not None else None,
                     "percentile": round(statistics.fmean(pcts)) if pcts else None,
                     "lower_is_better": METRICS[m][2] is False})
    return rows


def tendencies(valid):
    out = {}
    for t, parts in TENDENCIES.items():
        vals = []
        for _, s in valid:
            num = sum((s["pct"][m] if w > 0 else 100 - s["pct"][m]) * abs(w) for m, w in parts.items() if m in s["pct"])
            den = sum(abs(w) for m, w in parts.items() if m in s["pct"])
            if den:
                vals.append(num / den)
        if not vals:
            continue
        # pull small samples toward the middle so 3 games can't produce an extreme label
        n = len(vals)
        v = (statistics.fmean(vals) * n + 50 * 4) / (n + 4)
        hi, lo = TENDENCY_TEXT[t]
        out[t] = {"score": round(v), "text": hi if v >= 60 else lo if v <= 40 else "About average for your rank and role."}
    return out


def sessions(scored):
    """Hidden tendencies from the order of games: tilt, session length, time of day, surrenders."""
    games = [(g, s) for g, s in scored]
    if len(games) < 4:
        return {}
    after_win, after_loss, by_index = [], [], defaultdict(list)
    sess_len, cur, prev = [], 0, None
    two_loss_continue, two_loss_total = 0, 0
    for i, (g, s) in enumerate(games):
        new = prev is None or g["game_start"] - prev["game_end"] > SESSION_GAP
        if new:
            if cur:
                sess_len.append(cur)
            cur = 0
        cur += 1
        if s and s["overall"] is not None:
            by_index[min(cur, 4)].append(s["overall"])
            if not new and prev is not None:
                (after_win if prev["win"] else after_loss).append(s["overall"])
        if i >= 1 and not games[i][0]["win"] and not games[i - 1][0]["win"]:
            two_loss_total += 1
            nxt = games[i + 1][0] if i + 1 < len(games) else None
            if nxt and nxt["game_start"] - g["game_end"] <= SESSION_GAP:
                two_loss_continue += 1
        prev = g
    sess_len.append(cur)
    mean = lambda v: round(statistics.fmean(v)) if v else None
    return {
        "score_after_win": mean(after_win), "score_after_loss": mean(after_loss),
        "games_after_win": len(after_win), "games_after_loss": len(after_loss),
        "score_by_game_in_session": {("4+" if k == 4 else str(k)): mean(v) for k, v in sorted(by_index.items())},
        "avg_session_games": round(statistics.fmean(sess_len), 1),
        "kept_playing_after_two_losses": f"{two_loss_continue}/{two_loss_total}",
        "early_surrender_rate": round(sum(g["early_surrender"] for g, _ in games) / len(games), 3),
        "game_times": [{"start": g["game_start"], "win": g["win"], "score": round(s["overall"]) if s and s["overall"] else None}
                       for g, s in games],
    }


def champion_pool(valid, mastery):
    by = defaultdict(list)
    for g, s in valid:
        by[g["champion_id"]].append((g, s))
    mast = {m["championId"]: m for m in mastery}
    pool = []
    for cid, rows in by.items():
        n = len(rows)
        wins = sum(g["win"] for g, _ in rows)
        score = statistics.fmean(s["overall"] for _, s in rows)
        roles = Counter(g["role"] for g, _ in rows)
        role = roles.most_common(1)[0][0]
        info = CHAMPS.get(str(cid), {})
        cr = info.get("roles", {}).get(role, {})
        asp = defaultdict(list)
        for _, s in rows:
            for a, v in s["aspects"].items():
                asp[a].append(v)
        best = max(asp, key=lambda a: statistics.fmean(asp[a])) if asp else None
        worst = min(asp, key=lambda a: statistics.fmean(asp[a])) if asp else None
        if n >= 3 and score >= 55:
            verdict = "Core pick: you play it above your rank."
        elif n >= 3 and score <= 42:
            verdict = "Struggling: it may be costing you games."
        elif n < 3 and score >= 58:
            verdict = "Promising: play more games on it."
        else:
            verdict = "Solid: about your usual level."
        m = mast.get(cid, {})
        pool.append({"champion_id": cid, "champion": rows[0][0]["champion"],
                     "name": KEY_NAME.get(rows[0][0]["champion"], rows[0][0]["champion"]), "role": role, "games": n, "wins": wins,
                     "score": round(score), "best_aspect": best, "worst_aspect": worst, "verdict": verdict,
                     "mastery_level": m.get("championLevel"), "mastery_points": m.get("championPoints"),
                     "class": cr.get("class"), "scaling": cr.get("scaling"),
                     "hard_matchups": named(cr.get("hard_matchups", [])), "similar": named(cr.get("similar", []))})
    pool.sort(key=lambda p: (-p["games"], -p["score"]))
    played = {p["champion_id"] for p in pool}
    names = {int(k): v["name"] for k, v in CHAMPS.items()}
    legacy = [{"champion": names.get(m["championId"], str(m["championId"])), "mastery_points": m["championPoints"],
               "last_play": m.get("lastPlayTime", 0) / 1000}
              for m in sorted(mastery, key=lambda m: -m.get("championPoints", 0))[:15] if m["championId"] not in played][:6]
    # suggestions: champions similar to the player's best performers that they don't play yet
    tops = [p for p in pool if p["games"] >= 2 and p["score"] >= 52] or pool[:2]
    played_keys = {p["champion"].lower() for p in pool}
    sugg = []
    for p in tops[:3]:
        for s in p["similar"]:
            if s["key"].lower() not in played_keys and s["key"] not in [x["key"] for x in sugg]:
                sugg.append({"key": s["key"], "champion": s["name"], "because": KEY_NAME.get(p["champion"], p["champion"])})
                break
    total = sum(p["games"] for p in pool) or 1
    return {"champions": pool, "legacy": legacy, "suggestions": sugg,
            "unique_champions": len(pool), "top_share": round(pool[0]["games"] / total, 2) if pool else 0}


def traits(report, valid):
    """Readable labels from aspects, tendencies and habits. Each comes with the evidence."""
    out = []
    asp = {a: v["percentile"] for a, v in report["aspects"].get("aspects", {}).items()}
    ten = {t: v["score"] for t, v in report["tendencies"].items()}
    ses = report["sessions"]
    pool = report["champion_pool"]

    def add(name, why):
        out.append({"trait": name, "why": why})

    if asp.get("Laning", 50) >= 65 and ten.get("Aggression", 50) >= 55:
        add("Lane Bully", f"Laning {asp['Laning']}th percentile with aggressive early play.")
    if asp.get("Laning", 50) <= 40 and asp.get("Fighting", 50) >= 55:
        add("Late Bloomer", "Behind in lane, but you make it up in fights.")
    if ten.get("Roaming", 50) >= 65:
        add("Roamer", "You often get takedowns away from your own lane before 14:00.")
    if asp.get("Vision", 50) >= 65:
        add("Vision Controller", f"Vision {asp['Vision']}th percentile for your rank and role.")
    if asp.get("Objectives", 50) >= 65:
        add("Objective Player", "You're there for most of your team's dragons, grubs, heralds and barons.")
    if asp.get("Survival", 50) <= 35:
        add("Risky", "You die more often and earlier than players at your level.")
    if asp.get("Survival", 50) >= 65:
        add("Hard to Kill", "You die less than most players at your rank.")
    if ten.get("Resource focus", 50) >= 65 and asp.get("Fighting", 50) >= 55:
        add("Carry", "You take a big share of team gold and turn it into damage.")
    if ten.get("Teamfight focus", 50) >= 65:
        add("Teamfighter", "You show up for most 5v5 fights.")
    if pool.get("top_share", 0) >= 0.6 and pool.get("champions"):
        add("One-Trick", f"{round(pool['top_share'] * 100)}% of your games are on {pool['champions'][0]['champion']}.")
    if pool.get("unique_champions", 0) >= 10:
        add("Champion Ocean", f"{pool['unique_champions']} different champions in your recent games.")
    if ses.get("score_after_loss") is not None and ses.get("score_after_win") is not None \
            and ses["games_after_loss"] >= 3 and ses["games_after_win"] >= 3:
        d = ses["score_after_loss"] - ses["score_after_win"]
        if d <= -8:
            add("Tilts After Losses", f"Your games right after a loss score {-d} points lower than games after a win.")
        elif d >= 5:
            add("Resilient", "You play as well, or better, right after a loss.")
    k, t = map(int, ses.get("kept_playing_after_two_losses", "0/0").split("/"))
    if t >= 2 and k / t >= 0.7:
        add("Loss Chaser", f"You kept queueing after two losses in a row {k} of {t} times.")
    by_idx = ses.get("score_by_game_in_session", {})
    if by_idx.get("1") is not None and by_idx.get("4+") is not None and by_idx["4+"] <= by_idx["1"] - 8:
        add("Fades in Long Sessions", "From the 4th game in a row, your games score noticeably lower.")
    return out
