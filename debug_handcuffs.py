"""
Diagnostic script for the injury-driven pickups feature. Run this after
you've loaded the app at least once (so the player cache exists) to see
exactly where the pipeline is coming up empty, instead of guessing.

Usage:
    python3 debug_handcuffs.py <league_id>
"""
import sys

import recommender as r
import sleeper_client as sc


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 debug_handcuffs.py <league_id>")
        sys.exit(1)
    league_id = sys.argv[1]

    print("Fetching league rosters and player dictionary...")
    rosters = sc.get_rosters(league_id)
    players = sc.get_all_players()
    rostered_ids = r.rostered_player_ids(rosters)

    print(f"\nTotal players in Sleeper's dictionary: {len(players)}")
    print(f"Total rostered players in this league (across all teams): {len(rostered_ids)}")

    # Stage 1: are there any rostered players flagged as out at all?
    injured_rostered = [
        (pid, p)
        for pid, p in players.items()
        if pid in rostered_ids and p.get("injury_status") in r.INJURY_STATUSES_OUT
    ]
    print(f"\n[Stage 1] Rostered players currently marked {sorted(r.INJURY_STATUSES_OUT)}: "
          f"{len(injured_rostered)}")
    for pid, p in injured_rostered[:30]:
        print(
            f"  - {p.get('full_name')} ({p.get('team')} {p.get('position')}) "
            f"status={p.get('injury_status')!r} depth_chart_order={p.get('depth_chart_order')}"
        )
    if not injured_rostered:
        print("  -> Nothing here means either no one in your league is currently flagged,")
        print("     or Sleeper's actual status strings don't match what the code expects.")
        print("     Run this to see what values actually appear in the data:")
        statuses = {p.get("injury_status") for p in players.values() if p.get("injury_status")}
        print(f"     All distinct injury_status values in the dataset: {sorted(statuses)}")

    # Stage 2: for those players, is there a healthy player ahead of them?
    print("\n[Stage 2] For each injured rostered player, checking depth chart position...")
    for pid, p in injured_rostered[:30]:
        team, pos, order = p.get("team"), p.get("position"), p.get("depth_chart_order")
        if order is None:
            print(f"  - {p.get('full_name')}: no depth_chart_order -> goes to search_rank fallback")
            continue
        full = [
            (o, players.get(other_pid, {}).get("full_name"), players.get(other_pid, {}).get("injury_status"))
            for other_pid, other_p in players.items()
            if other_p.get("team") == team and other_p.get("position") == pos
            and other_p.get("depth_chart_order") is not None
            for o in [other_p.get("depth_chart_order")]
        ]
        full.sort()
        print(f"  - {p.get('full_name')} (order={order}) -- full {team} {pos} depth chart: {full}")

    # Stage 3: actual function output
    print("\n[Stage 3] Running find_handcuff_pickups()...")
    handcuffs = r.find_handcuff_pickups(players, rostered_ids)
    print(f"Result: {len(handcuffs)} handcuff(s) found")
    for h in handcuffs:
        print(f"  - {h}")


if __name__ == "__main__":
    main()
