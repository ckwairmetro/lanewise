"""Small Riot API client: per-host rate limiting from response headers, plus a SQLite cache.

Finished matches and timelines never change, so they are cached permanently. Rank, mastery and
match lists are cached for a few minutes. That keeps a repeat lookup to a handful of requests.
"""
import collections
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from urllib.parse import quote

import requests

PLATFORMS = {
    "euw1": ("europe", "EUW"), "eun1": ("europe", "EUNE"), "tr1": ("europe", "TR"), "ru": ("europe", "RU"),
    "na1": ("americas", "NA"), "br1": ("americas", "BR"), "la1": ("americas", "LAN"), "la2": ("americas", "LAS"),
    "kr": ("asia", "KR"), "jp1": ("asia", "JP"),
    "oc1": ("sea", "OCE"), "sg2": ("sea", "SG"), "tw2": ("sea", "TW"), "vn2": ("sea", "VN"),
}
SHORT_TTL = 600


class RiotError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class Limiter:
    """Sliding windows for every (count, seconds) pair the API reports for this host."""

    def __init__(self):
        self.limits = [(18, 1.0), (95, 120.0)]          # development-key defaults until headers arrive
        self.stamps = collections.deque()
        self.lock = threading.Lock()
        self.blocked_until = 0.0

    def update(self, header):
        try:
            lim = [(max(1, int(c) - max(1, int(c) // 20)), float(s)) for c, s in (p.split(":") for p in header.split(","))]
        except ValueError:
            return
        with self.lock:
            self.limits = lim

    def acquire(self):
        while True:
            with self.lock:
                now = time.time()
                wait = max(0.0, self.blocked_until - now)
                horizon = max(s for _, s in self.limits)
                while self.stamps and now - self.stamps[0] > horizon:
                    self.stamps.popleft()
                for count, secs in self.limits:
                    recent = [t for t in self.stamps if now - t < secs]
                    if len(recent) >= count:
                        wait = max(wait, secs - (now - recent[0]) + 0.05)
                if wait <= 0:
                    self.stamps.append(now)
                    return
            time.sleep(min(wait, 2.0))

    def block(self, secs):
        with self.lock:
            self.blocked_until = max(self.blocked_until, time.time() + secs)


class Riot:
    def __init__(self, api_key=None, cache_path=None):
        self.key = api_key or os.environ.get("RIOT_API_KEY")
        if not self.key:
            raise RuntimeError("Set RIOT_API_KEY (see .env.example)")
        self.session = requests.Session()
        self.session.headers["X-Riot-Token"] = self.key
        self.limiters = collections.defaultdict(Limiter)
        path = cache_path or Path(os.environ.get("LANEWISE_CACHE", "cache")) / "lanewise.sqlite"
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self.db.execute("CREATE TABLE IF NOT EXISTS cache(k TEXT PRIMARY KEY, t REAL, v TEXT)")
        self.db_lock = threading.Lock()

    # ------------------------------------------------------------------ http + cache
    def _cached(self, key, ttl):
        with self.db_lock:
            row = self.db.execute("SELECT t, v FROM cache WHERE k=?", (key,)).fetchone()
        if row and (ttl is None or time.time() - row[0] < ttl):
            return json.loads(row[1])
        return None

    def _store(self, key, value):
        with self.db_lock:
            self.db.execute("INSERT OR REPLACE INTO cache VALUES(?,?,?)", (key, time.time(), json.dumps(value)))
            self.db.commit()

    def get(self, host, path, params=None, ttl=SHORT_TTL):
        key = f"{host}{path}?{json.dumps(params, sort_keys=True) if params else ''}"
        hit = self._cached(key, ttl)
        if hit is not None:
            return hit
        for attempt in range(5):
            self.limiters[host].acquire()
            r = self.session.get(f"https://{host}.api.riotgames.com{path}", params=params, timeout=20)
            if "X-App-Rate-Limit" in r.headers:
                self.limiters[host].update(r.headers["X-App-Rate-Limit"])
            if r.status_code == 200:
                data = r.json()
                self._store(key, data)
                return data
            if r.status_code == 429:
                self.limiters[host].block(float(r.headers.get("Retry-After", 5)))
                continue
            if r.status_code == 404:
                return None
            if r.status_code in (401, 403):
                raise RiotError(r.status_code, "The API key was rejected (expired or invalid).")
            if r.status_code >= 500:
                time.sleep(1 + attempt)
                continue
            raise RiotError(r.status_code, f"Riot API error {r.status_code}")
        raise RiotError(503, "Riot API is busy, try again shortly.")

    # ------------------------------------------------------------------ endpoints
    def account(self, platform, game_name, tag_line):
        region = PLATFORMS[platform][0]
        return self.get(region, f"/riot/account/v1/accounts/by-riot-id/{quote(game_name)}/{quote(tag_line)}", ttl=86400)

    def league(self, platform, puuid):
        return self.get(platform, f"/lol/league/v4/entries/by-puuid/{puuid}") or []

    def mastery(self, platform, puuid):
        return self.get(platform, f"/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}") or []

    def match_ids(self, platform, puuid, count=20, queue=420):
        region = PLATFORMS[platform][0]
        return self.get(region, f"/lol/match/v5/matches/by-puuid/{puuid}/ids",
                        {"queue": queue, "start": 0, "count": count}) or []

    def match(self, platform, match_id):
        return self.get(PLATFORMS[platform][0], f"/lol/match/v5/matches/{match_id}", ttl=None)

    def timeline(self, platform, match_id):
        return self.get(PLATFORMS[platform][0], f"/lol/match/v5/matches/{match_id}/timeline", ttl=None)
