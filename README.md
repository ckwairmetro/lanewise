# Lanewise

**See how you really play.** Lanewise reads your recent ranked solo/duo games and compares every
part of your game with players at **your rank, in your role, on your champions**. Then it shows
where you spend your time on the map, which champions are working for you, and the habits behind
your results.

## Features

| | |
|---|---|
| **Skill breakdown** | Seven aspects: Laning, Farming, Fighting, Survival, Vision, Objectives and Teamplay. Each is a percentile against players of your tier and role, with champion differences removed: a Soraka isn't expected to farm like a Jinx. Every aspect lists its measures: your value, the typical value at your rank, and your percentile. |
| **Heatmap** | Your position every minute, from match timelines, drawn over the minimap with kills and deaths marked. Filter by game phase (laning, mid, late) or by champion. Red-side games can be flipped so your base is always bottom-left. |
| **Champion pool** | For each champion: games, win rate and a score against similar players. Also its best and worst aspect, a verdict (core / promising / solid / struggling), its class and scaling type, and the lane matchups to watch. It suggests champions that play like your best ones, and lists high-mastery champions you've stopped playing. |
| **Traits & habits** | Play-style tendencies such as aggression, roaming, teamfight vs skirmish, resource focus, invading, vision and communication. Readable traits such as Lane Bully, Roamer, One-Trick, Hard to Kill and Tilts After Losses, each with its evidence. Session habits: performance after a win vs after a loss, by game number in a session, and by hour of day; whether you keep queueing after two losses; early surrender rate. |
| **Match list** | Recent games with K/D/A, CS, lane opponent and a per-game score. |

## How the comparisons work

* Every metric is computed per game from match-v5 data and the match timeline. Examples: gold, XP
  and CS difference to the lane opponent at 10 and 15 minutes; damage per minute; vision score per
  minute; first death time; objective presence, meaning the share of your team's epic monsters you
  were part of.
* `lanewise/data/benchmarks.json` holds, for each tier and role, the distribution (5th to 95th
  percentile) of every metric in real ranked games. Games are bucketed by their lobby's average
  rank. Skill metrics are adjusted for champion first, using per-champion offsets with shrinkage.
* A game's aspect score is the weighted average of its metric percentiles. Your aspect score is the
  average over your games, so 50 means typical for your rank.
* Tendencies use the same percentiles without the champion adjustment, because picking aggressive
  champions *is* part of your style. They're pulled toward 50 when there are only a few games, so
  three games can't give you an extreme label.
* The benchmark files contain aggregates only: no player names, IDs or individual games.
  `tools/build_benchmarks.py` rebuilds them from a ranked-game corpus; see `docs/BENCHMARKS.md`.

## Riot API usage

| API | Used for |
|---|---|
| ACCOUNT-V1 `by-riot-id` | Turn a Riot ID into a PUUID |
| LEAGUE-V4 `entries/by-puuid` | Solo queue rank, to pick the comparison group |
| CHAMPION-MASTERY-V4 `by-puuid` | Mastery and last-played dates for the champion pool |
| MATCH-V5 `ids`, `matches`, `timeline` | Recent ranked games and minute-by-minute positions and events |

One report is about 2 × games + 4 requests, so 44 for 20 games. Finished matches and timelines are
cached permanently in `cache/`. Rank, mastery and match lists are cached for 10 minutes. The
client follows the `X-App-Rate-Limit` headers for each routing host and backs off on 429.

## Run it

Requires Python 3.10+.

```bash
python -m venv .venv
```

```bash
.venv\Scripts\activate
```

On macOS/Linux, activate with `source .venv/bin/activate` instead.

```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env
```

Put your key in `.env`, then start the app:

```bash
python run.py
```

Then open http://127.0.0.1:5000, enter a Riot ID (`Name#TAG`) and pick the region.

## Project layout

```
lanewise/
  app.py          Flask app: page + /api/report + /api/meta
  riot.py         API client: per-host rate limits from headers, SQLite cache
  extract.py      match + timeline -> per-game numbers and map positions
  metrics.py      metric, aspect and tendency definitions (shared with the benchmark builder)
  analysis.py     percentiles, aspects, tendencies, traits, sessions, champion pool
  data/           benchmarks.json, champions.json (aggregates)
  static/         index.html, app.js, style.css (no build step, no front-end dependencies)
tools/
  build_benchmarks.py
tests/
  test_analysis.py
```

Run the tests with:

```bash
python -m pytest tests
```

## Legal

Lanewise isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or
anyone officially involved in producing or managing Riot Games properties. Riot Games, and all
associated properties are trademarks or registered trademarks of Riot Games, Inc.

Champion icons and the minimap image are loaded from Riot's Data Dragon CDN.
