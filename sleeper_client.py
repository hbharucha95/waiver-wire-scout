"""
Thin client for Sleeper's public, unauthenticated API.
Docs: https://docs.sleeper.com/

No API key or login required -- this is why multi-user support is low-lift:
any user just needs to tell us their Sleeper username or league ID.
"""
from __future__ import annotations  # lets `dict | None` type hints work on Python 3.9

import json
import time
from pathlib import Path

import requests

BASE = "https://api.sleeper.app/v1"
CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
PLAYERS_CACHE_FILE = CACHE_DIR / "players_nfl.json"
PLAYERS_CACHE_MAX_AGE_HOURS = 24  # Sleeper: this file changes rarely, don't re-fetch often


def _get(path: str, params: dict | None = None) -> dict | list:
    resp = requests.get(f"{BASE}{path}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_user(username_or_id: str) -> dict:
    """Look up a Sleeper user by username or user_id."""
    return _get(f"/user/{username_or_id}")


def get_user_leagues(user_id: str, season: str, sport: str = "nfl") -> list[dict]:
    """All of a user's leagues for a given season."""
    return _get(f"/user/{user_id}/leagues/{sport}/{season}")


def get_league(league_id: str) -> dict:
    return _get(f"/league/{league_id}")


def get_rosters(league_id: str) -> list[dict]:
    return _get(f"/league/{league_id}/rosters")


def get_league_users(league_id: str) -> list[dict]:
    return _get(f"/league/{league_id}/users")


def get_trending_adds(lookback_hours: int = 48, limit: int = 25) -> list[dict]:
    """Real-time signal: players being added across Sleeper leagues right now."""
    return _get(
        "/players/nfl/trending/add",
        params={"lookback_hours": lookback_hours, "limit": limit},
    )


def get_all_players(force_refresh: bool = False) -> dict:
    """
    The full NFL player dictionary, keyed by player_id. This is a large file
    (thousands of players) that Sleeper says changes infrequently -- cache it
    to disk instead of re-fetching on every request. This mirrors a real
    build finding: fetching this file ad hoc doesn't scale, it needs a
    proper cache.
    """
    if not force_refresh and PLAYERS_CACHE_FILE.exists():
        age_hours = (time.time() - PLAYERS_CACHE_FILE.stat().st_mtime) / 3600
        if age_hours < PLAYERS_CACHE_MAX_AGE_HOURS:
            with open(PLAYERS_CACHE_FILE) as f:
                return json.load(f)

    players = _get("/players/nfl")
    with open(PLAYERS_CACHE_FILE, "w") as f:
        json.dump(players, f)
    return players
