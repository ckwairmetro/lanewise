"""Build lanewise/data/benchmarks.json and champions.json from a crawled ranked-game corpus.

The shipped JSON files are aggregates only: per-game metric quantiles for each tier and role,
champion offsets, and champion-level tables. No player identities are included.

Input: per-player-game parquet tables of ranked solo games plus each server's league table
(produced by a separate crawler; see docs/BENCHMARKS.md). Games are bucketed by the average
rank of their lobby.

Usage: python tools/build_benchmarks.py --ladder "D:/League Manager/Ladder/data"
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lanewise.metrics import METRICS, ROLES  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "lanewise" / "data"
QS = list(range(0, 101, 5))
PINGS = ["allInPings", "assistMePings", "basicPings", "commandPings", "dangerPings", "enemyMissingPings",
         "enemyVisionPings", "getBackPings", "holdPings", "needVisionPings", "onMyWayPings", "pushPings",
         "retreatPings", "visionClearedPings"]


def tier_of(points):
    t = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND"]
    return np.where(points >= 2800, "MASTER+", np.array(t)[np.clip(points // 400, 0, 6).astype(int)])


def load(ladder):
    frames = []
    servers = [ladder] + [p for p in ladder.iterdir() if p.is_dir() and (p / "ladder.sqlite").exists()]
    for d in servers:
        con = sqlite3.connect(f"file:{(d / 'ladder.sqlite').as_posix()}?mode=ro", uri=True)
        pts = dict(con.execute("SELECT puuid, points FROM league WHERE queue='RANKED_SOLO_5x5'").fetchall())
        for f in sorted((d / "tables" / "player_games").glob("cascade-*.parquet")):
            g = pd.read_parquet(f)
            g["rank_pts"] = g["puuid"].map(pts)
            lob = g.groupby("match_id")["rank_pts"].mean()
            g["lobby"] = g["match_id"].map(lob)
            frames.append(g.dropna(subset=["lobby"]))
    # Master+ corpus: a sample is plenty for the top bucket
    ms = sorted((ladder / "tables" / "player_games").glob("matchsim-*.parquet"))[:6]
    for f in ms:
        g = pd.read_parquet(f)
        g["lobby"] = 3000.0
        frames.append(g)
    df = pd.concat(frames, ignore_index=True)
    df = df[df["role"].isin(ROLES) & ~df["early_ff"].astype(bool)].copy()
    df["pings"] = df[PINGS].sum(axis=1)
    df["first_death_min"] = df["first_death"].fillna(df["minutes"]).clip(upper=25)
    df["tier"] = tier_of(df["lobby"].to_numpy())
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ladder", required=True, type=Path)
    a = ap.parse_args()
    df = load(a.ladder)
    vals = pd.DataFrame({m: pd.to_numeric(fn(df), errors="coerce") for m, (_, fn, _) in METRICS.items()}, index=df.index)
    vals = vals.astype(float).replace([np.inf, -np.inf], np.nan)

    # champion offsets (skill metrics only): champion mean minus role mean, shrunk with 25 pseudo-games
    offsets = {}
    for role in ROLES:
        sub = vals[df["role"] == role]
        champ = df.loc[sub.index, "champion_id"]
        rm = sub.mean()
        g = sub.groupby(champ)
        n = g.count()
        off = ((g.mean() - rm) * n / (n + 25)).round(4)
        keep = [m for m, (_, _, b) in METRICS.items() if b is not None]
        offsets[role] = {int(c): {m: float(v) for m, v in row[keep].items() if np.isfinite(v)} for c, row in off.iterrows()}
    adj = vals.copy()
    for role in ROLES:
        idx = df.index[df["role"] == role]
        for m, (_, _, b) in METRICS.items():
            if b is None:
                continue
            o = df.loc[idx, "champion_id"].map(lambda c: offsets[role].get(int(c), {}).get(m, 0.0))
            adj.loc[idx, m] = vals.loc[idx, m] - o

    bench = {"quantiles": QS, "tiers": {}, "counts": {}}
    for tier in sorted(df["tier"].unique()):
        bench["tiers"][tier] = {}
        bench["counts"][tier] = {}
        for role in ROLES:
            idx = df.index[(df["tier"] == tier) & (df["role"] == role)]
            bench["counts"][tier][role] = int(len(idx))
            if len(idx) < 40:
                continue
            bench["tiers"][tier][role] = {m: [round(float(v), 4) for v in np.nanpercentile(adj.loc[idx, m], QS)]
                                          for m in METRICS if adj.loc[idx, m].notna().sum() >= 30}
    bench["champion_offsets"] = offsets
    bench["games"] = int(df["match_id"].nunique())
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(bench, open(OUT / "benchmarks.json", "w"), separators=(",", ":"))
    print(f"benchmarks: {bench['games']:,} games; counts {bench['counts']}")
    champions(a.ladder)


def champions(ladder):
    """Per champion and role: class, scaling, strongest/weakest lane matchups, most similar picks."""
    c = ladder / "champions"
    if not (c / "classes.parquet").exists():
        print("no champion tables, skipping champions.json")
        return
    cls = pd.read_parquet(c / "classes.parquet")
    cr = pd.read_parquet(c / "champion_roles.parquet")
    cr = cr[cr["stratum"] == "all"]
    mu = pd.read_parquet(c / "matchups.parquet")
    mu = mu[(mu["stratum"] == "all") & (mu["n"] >= 30)]
    out = {}
    for role in ROLES:
        sim_path = c / f"similarity_{role}.parquet"
        sim = pd.read_parquet(sim_path).set_index("champion") if sim_path.exists() else None
        for _, r in cr[cr["role"] == role].iterrows():
            cid = int(r["champion_id"])
            k = cls[(cls["champion_id"] == cid) & (cls["role"] == role)]
            m = mu[(mu["champion_id"] == cid) & (mu["role"] == role)].sort_values("lane_delta_shrunk")
            entry = {"games": int(r["games"]), "win_rate": round(float(r["wr_shrunk"]), 4),
                     "class": k["class_label"].iloc[0] if len(k) else None,
                     "scaling": r.get("scaling_archetype"),
                     "hard_matchups": m.head(5)["opp_champion"].tolist(),
                     "easy_matchups": m.tail(5)["opp_champion"].tolist()[::-1]}
            key = r["champion"]
            if sim is not None and key in sim.index:
                s = sim.loc[key].drop(labels=[key], errors="ignore").sort_values(ascending=False)
                entry["similar"] = s.head(5).index.tolist()
            out.setdefault(str(cid), {"name": r.get("name") or key, "key": key, "roles": {}})["roles"][role] = entry
    json.dump(out, open(OUT / "champions.json", "w"), separators=(",", ":"))
    print(f"champions: {len(out)} champions")


if __name__ == "__main__":
    main()
