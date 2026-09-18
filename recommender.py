"""
Core recommendation logic. Deliberately simple for v1: this is a
prototype meant to demonstrate the concept end-to-end, not a
production-grade projections model.
"""
from __future__ import annotations  # lets `dict | None` type hints work on Python 3.9

FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}
POSITION_ORDER = ["QB", "RB", "WR", "TE", "K", "DEF"]  # standard fantasy display order
DST_ABBRS = {  # Sleeper represents team defenses by team abbreviation, not a numeric ID
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
    "DET", "GB", "HOU", "IND", "JAX", "KC", "LV", "LAC", "LAR", "MIA",
    "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SF", "SEA", "TB",
    "TEN", "WAS",
}


def group_by_position(entries: list[dict]) -> list[dict]:
    """Groups a list of player dicts (each with a 'position' key) into
    ordered {"position": ..., "players": [...]} groups, following the
    standard QB/RB/WR/TE/K/DEF fantasy display order, with anything
    unexpected sorted alphabetically at the end."""
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        groups.setdefault(entry["position"], []).append(entry)
    ordered = []
    for pos in POSITION_ORDER:
        if pos in groups:
            ordered.append({"position": pos, "players": groups.pop(pos)})
    for pos in sorted(groups):
        ordered.append({"position": pos, "players": groups[pos]})
    return ordered



HEADSHOT_URL_TEMPLATE = "https://sleepercdn.com/content/nfl/players/{}.jpg"


def player_name(player_id: str, players: dict) -> str:
    if player_id in DST_ABBRS:
        return f"{player_id} D/ST"
    p = players.get(player_id)
    if not p:
        return f"Unknown ({player_id})"
    return p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()


def player_position(player_id: str, players: dict) -> str:
    if player_id in DST_ABBRS:
        return "DEF"
    p = players.get(player_id, {})
    return p.get("position") or "?"


def player_team(player_id: str, players: dict) -> str:
    if player_id in DST_ABBRS:
        return player_id
    p = players.get(player_id, {})
    return p.get("team") or "FA"


def player_headshot_url(player_id: str, players: dict) -> str | None:
    """
    Undocumented but widely relied-upon Sleeper CDN pattern for individual
    player headshots. Sleeper doesn't publish this officially, so treat it
    as best-effort -- the template's <img onerror> hides it if a given ID
    doesn't resolve. Team defenses have no individual headshot.
    """
    if player_id in DST_ABBRS:
        return None
    return HEADSHOT_URL_TEMPLATE.format(player_id)


def rostered_player_ids(rosters: list[dict]) -> set[str]:
    ids = set()
    for r in rosters:
        for pid in r.get("players") or []:
            ids.add(pid)
    return ids


def find_my_roster(rosters: list[dict], owner_id: str) -> dict | None:
    for r in rosters:
        if r.get("owner_id") == owner_id:
            return r
    return None


def free_agents_from_trending(
    trending: list[dict], rostered_ids: set[str], players: dict
) -> list[dict]:
    """Trending adds that are NOT already rostered by anyone in the league."""
    out = []
    for entry in trending:
        pid = entry["player_id"]
        if pid in rostered_ids:
            continue
        pos = player_position(pid, players)
        if pos not in FANTASY_POSITIONS:
            continue
        out.append(
            {
                "player_id": pid,
                "name": player_name(pid, players),
                "position": pos,
                "team": player_team(pid, players),
                "headshot_url": player_headshot_url(pid, players),
                "add_count": entry["count"],
            }
        )
    return out


def bench_context(roster: dict, players: dict) -> list[dict]:
    """
    The user's own bench: starters are excluded, everything else is bench/reserve.
    Players in a dedicated reserve/IR slot are flagged `is_reserve` -- they don't
    occupy a normal bench spot, so they shouldn't be suggested as drops to make
    room for a new add.
    """
    starters = set(roster.get("starters") or [])
    reserve_ids = set(roster.get("reserve") or [])
    bench = []
    for pid in roster.get("players") or []:
        if pid in starters:
            continue
        p = players.get(pid, {}) if pid not in DST_ABBRS else {}
        bench.append(
            {
                "player_id": pid,
                "name": player_name(pid, players),
                "position": player_position(pid, players),
                "team": player_team(pid, players),
                "headshot_url": player_headshot_url(pid, players),
                "injury_status": p.get("injury_status"),
                "depth_chart_position": p.get("depth_chart_position"),
                "is_reserve": pid in reserve_ids,
            }
        )
    return bench


INJURY_STATUSES_OUT = {"Out", "IR", "PUP", "Doubtful", "Suspended"}
NO_RANK_SENTINEL = 9999999  # Sleeper's placeholder for "not meaningfully ranked"


def find_handcuff_pickups(
    players: dict, rostered_ids: set[str], limit: int = 5
) -> list[dict]:
    """
    Proactive signal, independent of trending-add lag: for every fantasy-relevant
    player currently marked Out/IR/Doubtful/etc, find the next player on that
    same team's depth chart at the same position who is NOT already rostered
    by anyone in the league and is themselves actually available.

    depth_chart_order is Sleeper's primary signal for this, but it's null for
    a large share of players. When it's missing (for the injured player or for
    every qualifying candidate), fall back to search_rank -- Sleeper's general
    fantasy-relevance ranking, tracked far more consistently -- to find the
    best-regarded available free agent at that team+position instead.
    """
    by_team_pos_depth = {}       # (team, position) -> free-agent candidates by depth order
    full_depth_by_team_pos = {}  # (team, position) -> everyone, for "who's ahead" checks
    by_team_pos_rank = {}        # (team, position) fallback via search_rank
    for pid, p in players.items():
        team = p.get("team")
        pos = p.get("position")
        if not team or pos not in FANTASY_POSITIONS:
            continue

        order = p.get("depth_chart_order")
        if order is not None:
            full_depth_by_team_pos.setdefault((team, pos), []).append((order, pid))
            if pid not in rostered_ids:
                by_team_pos_depth.setdefault((team, pos), []).append((order, pid))

        if pid in rostered_ids:
            continue
        rank = p.get("search_rank")
        if rank is not None and rank != NO_RANK_SENTINEL:
            by_team_pos_rank.setdefault((team, pos), []).append((rank, pid))

    for group in (by_team_pos_depth, full_depth_by_team_pos, by_team_pos_rank):
        for key in group:
            group[key].sort()

    def someone_healthy_ahead(team: str, pos: str, order: int) -> bool:
        """True if anyone higher on this team's depth chart at this position
        (rostered or not) is currently available -- meaning the role hasn't
        actually opened up."""
        for o, other_pid in full_depth_by_team_pos.get((team, pos), []):
            if o >= order:
                continue
            if players.get(other_pid, {}).get("injury_status") not in INJURY_STATUSES_OUT:
                return True
        return False

    def first_available(candidates: list[tuple], min_value: float = float("-inf")):
        for value, cand_pid in candidates:
            if value <= min_value:
                continue
            cand_status = players.get(cand_pid, {}).get("injury_status")
            if cand_status in INJURY_STATUSES_OUT:
                continue
            return value, cand_pid
        return None

    handcuffs = []
    seen_backup_ids = set()
    for pid, p in players.items():
        # Deliberately NOT filtered to `pid in rostered_ids` here: a starter
        # getting hurt matters whether or not that starter happens to be
        # rostered in this specific league. Restricting to this league's
        # ~150-200 rostered players misses the vast majority of the NFL's
        # ~1,700 active players, and therefore misses most real "starter is
        # out" situations entirely.
        status = p.get("injury_status")
        if status not in INJURY_STATUSES_OUT:
            continue
        team, pos, order = p.get("team"), p.get("position"), p.get("depth_chart_order")
        if not team or pos not in FANTASY_POSITIONS:
            continue

        via = None
        next_up = None

        if order is not None:
            # We know where this player sat on the depth chart -- only
            # proceed if no one healthy remains ahead of them (otherwise
            # the starting role hasn't actually opened up).
            if someone_healthy_ahead(team, pos, order):
                continue
            next_up = first_available(by_team_pos_depth.get((team, pos), []), order)
            if next_up is not None:
                via = "depth_chart"

        if next_up is None:
            # Either depth_chart_order was missing for this player (we can't
            # tell whether they were "the starter"), or the role is confirmed
            # open but no depth-chart candidate was found -- fall back to
            # the best-ranked available free agent at this team+position.
            via = "search_rank"
            next_up = first_available(by_team_pos_rank.get((team, pos), []))

        if not next_up or next_up[1] in seen_backup_ids:
            continue
        seen_backup_ids.add(next_up[1])

        handcuffs.append(
            {
                "player_id": next_up[1],
                "name": player_name(next_up[1], players),
                "position": pos,
                "team": player_team(next_up[1], players),
                "headshot_url": player_headshot_url(next_up[1], players),
                "injured_starter": player_name(pid, players),
                "injured_starter_team": team,
                "injured_starter_status": status,
                "via": via,
                # Used only to prioritize below -- not shown to the user.
                "_injured_starter_rank": p.get("search_rank") or NO_RANK_SENTINEL,
            }
        )

    # Now scanning the whole NFL rather than just this league's ~150-200
    # rostered players, so sort by how notable the injured starter is
    # (lower search_rank = more relevant) before cutting to `limit`,
    # rather than taking whatever order the dictionary happened to iterate in.
    handcuffs.sort(key=lambda h: h["_injured_starter_rank"])
    for h in handcuffs:
        del h["_injured_starter_rank"]
    handcuffs = handcuffs[:limit]

    return handcuffs


def _format_news_recency(news_updated_ms: int | None) -> str | None:
    """
    Sleeper's news_updated is a Unix-ms timestamp of when this player's info
    last changed. It doesn't say anything about play probability, but it
    tells you how fresh (or stale) the injury_status/notes actually are --
    a report from an hour ago carries more weight than one from three days
    ago. Light-lift alternative to a fabricated "likelihood to play" score.
    """
    if not news_updated_ms:
        return None
    from datetime import datetime

    dt = datetime.fromtimestamp(news_updated_ms / 1000)
    return dt.strftime("%b %d, %I:%M %p").replace(" 0", " ")


def find_questionable_insurance(
    players: dict, rostered_ids: set[str], limit: int = 10
) -> list[dict]:
    """
    For every fantasy-relevant player currently listed Questionable -- across
    the whole NFL, not just this league's rostered players -- surface
    available injury context (body part, notes, practice participation if
    Sleeper has it) plus the best available free-agent "insurance" option at
    that spot, so the user can judge whether it's worth grabbing a
    just-in-case backup before kickoff.

    Not restricted to the user's own roster: a notable player being
    Questionable matters for insurance decisions whether or not that player
    happens to be on a roster in this specific league. "Fantasy-relevant" is
    approximated by having a real search_rank (Sleeper's general relevance
    signal) -- this keeps the list from being flooded with Questionable
    deep-bench players nobody would ever start anyway. Results are sorted by
    that relevance and cut to `limit`.
    """
    by_team_pos_depth = {}
    by_team_pos_rank = {}
    for pid, p in players.items():
        if pid in rostered_ids:
            continue
        team, pos = p.get("team"), p.get("position")
        if not team or pos not in FANTASY_POSITIONS:
            continue
        order = p.get("depth_chart_order")
        if order is not None:
            by_team_pos_depth.setdefault((team, pos), []).append((order, pid))
        rank = p.get("search_rank")
        if rank is not None and rank != NO_RANK_SENTINEL:
            by_team_pos_rank.setdefault((team, pos), []).append((rank, pid))
    for group in (by_team_pos_depth, by_team_pos_rank):
        for key in group:
            group[key].sort()

    def best_free_agent(team: str, pos: str, min_order: float):
        for order, cand_pid in by_team_pos_depth.get((team, pos), []):
            if order <= min_order:
                continue
            if players.get(cand_pid, {}).get("injury_status") in INJURY_STATUSES_OUT:
                continue
            return cand_pid
        for _, cand_pid in by_team_pos_rank.get((team, pos), []):
            if players.get(cand_pid, {}).get("injury_status") in INJURY_STATUSES_OUT:
                continue
            return cand_pid
        return None

    watchlist = []
    for pid, p in players.items():
        if pid in DST_ABBRS:
            continue
        if p.get("injury_status") != "Questionable":
            continue
        rank = p.get("search_rank")
        if rank is None or rank == NO_RANK_SENTINEL:
            continue  # not fantasy-relevant enough to bother surfacing
        team, pos, order = p.get("team"), p.get("position"), p.get("depth_chart_order")
        if not team or pos not in FANTASY_POSITIONS:
            continue

        backup_pid = best_free_agent(team, pos, order if order is not None else float("-inf"))

        watchlist.append(
            {
                "player_id": pid,
                "name": player_name(pid, players),
                "team": player_team(pid, players),
                "position": pos,
                "headshot_url": player_headshot_url(pid, players),
                "injury_body_part": p.get("injury_body_part"),
                "injury_notes": p.get("injury_notes"),
                "news_updated": _format_news_recency(p.get("news_updated")),
                "insurance": (
                    {
                        "player_id": backup_pid,
                        "name": player_name(backup_pid, players),
                        "team": player_team(backup_pid, players),
                        "headshot_url": player_headshot_url(backup_pid, players),
                    }
                    if backup_pid
                    else None
                ),
                # Used only to prioritize below -- not shown to the user.
                "_rank": rank,
            }
        )

    # Scanning the whole NFL rather than one roster surfaces far more
    # Questionable players than `limit` can show, so sort by relevance
    # (lower search_rank = more notable) before cutting, rather than
    # taking whatever order the dictionary happened to iterate in.
    watchlist.sort(key=lambda w: w["_rank"])
    for w in watchlist:
        del w["_rank"]
    watchlist = watchlist[:limit]

    return watchlist


def generate_recommendations(
    free_agents: list[dict], bench: list[dict], top_n: int = 5
) -> list[dict]:
    """
    v1 heuristic: rank free agents by trending add-count, then for each,
    suggest the weakest bench player at the same position as a drop
    candidate (weakest = flagged with an injury_status, otherwise just
    the first match). This is intentionally simple -- the point of v1
    is a working, explainable pipeline, not a sophisticated model.
    """
    recs = []
    for fa in sorted(free_agents, key=lambda x: -x["add_count"])[:top_n]:
        # Reserve/IR players are excluded: they sit in a separate roster slot,
        # so dropping them doesn't free up space the way a normal bench cut does.
        same_pos_bench = [
            b for b in bench if b["position"] == fa["position"] and not b["is_reserve"]
        ]
        drop_candidate = None
        for b in same_pos_bench:
            if b["injury_status"]:
                drop_candidate = b
                break
        if drop_candidate is None and same_pos_bench:
            drop_candidate = same_pos_bench[0]

        reason = (
            f"Being added in a large number of Sleeper leagues in the last 48 hours "
            f"({fa['add_count']:,} adds) -- a strong early signal of a role or "
            f"opportunity change before it's fully reflected in box scores."
        )
        if drop_candidate and drop_candidate["injury_status"]:
            reason += (
                f" Your {drop_candidate['name']} is currently listed as "
                f"{drop_candidate['injury_status']}, making this a reasonable swap."
            )

        recs.append(
            {
                "add": fa,
                "reason": reason,
                "drop_candidate": drop_candidate,
            }
        )
    return recs
