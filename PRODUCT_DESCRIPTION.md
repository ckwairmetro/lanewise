# Riot Developer Portal: product application

**Product Name:** Lanewise

**Product URL:** https://github.com/ckwairmetro/lanewise

**Product Description:**

Lanewise is a free personal improvement tool for League of Legends players of every rank. A player
enters their Riot ID and region, and Lanewise reads their recent ranked solo/duo games. It shows
how each part of their game compares with players at the same rank, in the same role, on the same
champions. Most stat sites show raw numbers ("6.1 CS per minute") without context. Lanewise puts
every number next to what is typical for a Gold top laner, a Diamond support and so on, adjusts it
for champion, and turns it into seven aspects: Laning, Farming, Fighting, Survival, Vision,
Objectives and Teamplay. The player sees at a glance whether they are weak or strong in each one.
Each aspect lists its measures (for example gold lead at 10 minutes, first death time, control
wards per minute, objective presence) and a short tip for the weakest areas.

Lanewise has four more views:
- **Heatmap:** the player's position every minute of their games, from match timelines, over the
  minimap. Kills and deaths are marked, and it can be filtered by game phase and champion. Players
  can see where they actually spend the laning phase, where they die, and where they win fights.
- **Champion pool manager:** per champion, games, win rate and a score against similar players,
  plus its best and worst aspect and a verdict (core, promising, solid, struggling). It also lists
  that champion's hard lane matchups, champions that play like the player's best ones, and
  high-mastery champions they have stopped playing.
- **Traits and habits:** play-style tendencies (aggression, roaming, teamfight vs skirmish,
  resource focus, invading, vision, communication) and readable traits with evidence, such as
  "Lane Bully", "One-Trick", "Hard to Kill" and "Tilts After Losses". It also shows patterns
  players rarely notice themselves: how they perform right after a loss compared with after a win,
  how their play changes over a long session and by hour of day, and how often they keep queueing
  after two losses in a row.
- **Match list:** recent games with K/D/A, CS, lane opponent and a per-game score.

The comparison data comes from aggregate statistics of ranked games across all tiers: per-tier,
per-role metric distributions and per-champion offsets. It holds no names or IDs of other players.
Lanewise only shows a player data about their own games, or games of a Riot ID they enter, using
information already public in match history. It has no ranking or comparison of named individuals
and no MMR estimation, and nothing in it gives an unfair in-game advantage. It is used between
games for review and improvement only.

**APIs used:**
- ACCOUNT-V1: Riot ID to PUUID.
- LEAGUE-V4: entries by PUUID, for the player's solo rank and so their comparison group.
- CHAMPION-MASTERY-V4: by PUUID, for the champion pool view.
- MATCH-V5: match IDs by PUUID (ranked solo queue), match details and match timelines, for all
  per-game metrics and the minute-by-minute positions behind the heatmap.

The aggregate benchmark tables are rebuilt periodically, about once per patch, from ranked games
collected with the same endpoints, plus LEAGUE-V4 for lobby ranks. The job is rate-limited and
cached.

A typical report takes about 44 requests (20 games: match + timeline each, plus account, league,
mastery and the match list). Finished matches and timelines are cached permanently, and rank,
mastery and match lists for 10 minutes, so repeat visits cost only a few requests. The client
follows the X-App-Rate-Limit headers per routing region and backs off on 429 responses (honouring
Retry-After). The API key stays on the server and is never sent to the browser.

The product is a web app: a Python (Flask) back end and a plain HTML/JavaScript front end. The
full source is public on GitHub at https://github.com/ckwairmetro/lanewise. The working prototype is
at commit 41e0621 (https://github.com/ckwairmetro/lanewise/commit/41e062183e85dd76a7e988ad55e40265c26185f0),
and the README explains how to run it. Lanewise is free, has no ads or paid features, and carries
Riot's legal boilerplate on every page.
