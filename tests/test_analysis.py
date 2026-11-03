"""Offline tests: a synthetic match + timeline through extraction and scoring (no API key needed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lanewise import analysis  # noqa: E402
from lanewise.extract import player_game, zone  # noqa: E402

ROLES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]


def participant(pid, team, role, puuid, champ="Ahri", champ_id=103, win=True):
    return {"participantId": pid, "teamId": team, "teamPosition": role, "puuid": puuid, "championId": champ_id,
            "championName": champ, "win": win, "kills": 5, "deaths": 3, "assists": 7, "goldEarned": 12000,
            "totalMinionsKilled": 200, "neutralMinionsKilled": 10, "totalDamageDealtToChampions": 22000,
            "damageDealtToTurrets": 3000, "damageDealtToEpicMonsters": 1500, "visionScore": 25, "wardsPlaced": 10,
            "wardsKilled": 3, "totalHealsOnTeammates": 0, "totalDamageShieldedOnTeammates": 0,
            "timeCCingOthers": 20, "champLevel": 16,
            "challenges": {"teamDamagePercentage": 0.25, "killParticipation": 0.55, "soloKills": 1}}


def fake_match():
    parts = [participant(i + 1, 100 if i < 5 else 200, ROLES[i % 5], f"p{i + 1}", win=i < 5) for i in range(10)]
    frames = []
    for m in range(31):
        pf = {str(p["participantId"]): {"totalGold": 500 + 400 * m + (50 * m if p["teamId"] == 100 else 0), "xp": 300 * m,
                                        "minionsKilled": 7 * m, "jungleMinionsKilled": 0,
                                        "position": {"x": 7000 + 10 * m, "y": 7000}} for p in parts}
        frames.append({"participantFrames": pf, "events": []})
    frames[8]["events"] = [{"type": "CHAMPION_KILL", "timestamp": 8 * 60000, "killerId": 3, "victimId": 8,
                            "assistingParticipantIds": [2], "position": {"x": 7400, "y": 7400}}]
    frames[12]["events"] = [{"type": "ELITE_MONSTER_KILL", "timestamp": 12 * 60000, "killerTeamId": 100, "killerId": 2,
                             "assistingParticipantIds": [3], "monsterType": "DRAGON"},
                            {"type": "WARD_PLACED", "timestamp": 12 * 60000, "creatorId": 3, "wardType": "CONTROL_WARD"}]
    match = {"metadata": {"matchId": "EUW1_1"}, "info": {"gameDuration": 1800, "gameStartTimestamp": 1_700_000_000_000,
                                                         "gameEndTimestamp": 1_700_001_800_000, "gameVersion": "16.21.1",
                                                         "queueId": 420, "participants": parts}}
    return match, {"info": {"frames": frames}}


def test_extract_and_score():
    match, tl = fake_match()
    g = player_game(match, tl, "p3")
    assert g["role"] == "MIDDLE" and g["opp_champion"] == "Ahri"
    assert g["gold10_diff"] == 500 and g["takedowns_pre14"] == 1 and g["obj_present"] == 1
    assert g["wards_control"] == 1 and len(g["positions"]) == 30
    s = analysis.score_game(g, analysis.bench_tier("GOLD"))
    assert s["aspects"] and 0 <= s["overall"] <= 100
    for v in s["pct"].values():
        assert 0 <= v <= 100


def test_zone_mirrors_red_side():
    assert zone(1000, 1000, 100) == "own_base"
    assert zone(1000, 1000, 200) == "enemy_base"


def test_bench_tier_fallbacks():
    assert analysis.bench_tier("CHALLENGER") == "MASTER+"
    assert analysis.bench_tier(None) in analysis.BENCH["tiers"]
