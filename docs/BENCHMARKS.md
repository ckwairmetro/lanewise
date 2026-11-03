# Benchmarks

`lanewise/data/benchmarks.json` is what "players like you" means in Lanewise.

## Contents

- `tiers[TIER][ROLE][metric]` holds 21 quantiles (0, 5, …, 100) of the per-game metric, from ranked
  solo games where the lobby's average rank falls in that tier. Apex tiers (Master, Grandmaster,
  Challenger) share the `MASTER+` bucket.
- `champion_offsets[ROLE][champion_id][metric]` is the champion's mean minus the role mean, shrunk
  toward 0 with 25 pseudo-games. Skill metrics are adjusted by this offset before they are
  compared, so supports aren't penalised for farming like supports.
- `counts[TIER][ROLE]` is the number of player-games in each bucket. If a bucket has fewer than 40,
  it is left empty and the app falls back to the nearest tier.

## Champion data

`lanewise/data/champions.json` holds per-champion, per-role data:
- shrunk win rate;
- class label, from clustering champions' matchup and synergy profiles;
- scaling type, from the shape of the team gold-lead curve;
- the five hardest and easiest lane matchups, from shrunk lane gold and XP deltas;
- the five most similar champions.

## Rebuilding

The tables are aggregates of public ranked match data. They contain no player names, IDs or
individual games.

`tools/build_benchmarks.py --ladder <folder>` reads two inputs:
- the per-player-game parquet tables and league snapshots written by a separate ranked-game crawler
  (same metric definitions: `lanewise/metrics.py`);
- that project's champion tables.

Rebuild about once per patch. To install its extra dependencies:

```bash
pip install -r requirements-tools.txt
```
