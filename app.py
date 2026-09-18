"""
Waiver Wire Scout -- v1 prototype

Run with: flask --app app run --debug
Then open http://127.0.0.1:5000
"""
from datetime import datetime

from flask import Flask, redirect, render_template, request, url_for

import recommender
import sleeper_client as sc

app = Flask(__name__)
CURRENT_SEASON = "2026"


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/leagues", methods=["POST"])
def leagues():
    username = request.form.get("username", "").strip()
    if not username:
        return render_template("index.html", error="Enter a Sleeper username.")

    try:
        user = sc.get_user(username)
        user_leagues = sc.get_user_leagues(user["user_id"], CURRENT_SEASON)
    except Exception:
        return render_template(
            "index.html", error=f"Couldn't find a Sleeper user '{username}'."
        )

    if not user_leagues:
        return render_template(
            "index.html", error=f"No {CURRENT_SEASON} leagues found for '{username}'."
        )

    return render_template(
        "leagues.html",
        username=username,
        user_id=user["user_id"],
        leagues=user_leagues,
    )


@app.route("/recommendations", methods=["POST"])
def recommendations():
    league_id = request.form.get("league_id")
    user_id = request.form.get("user_id")
    username = request.form.get("username")

    league = sc.get_league(league_id)
    rosters = sc.get_rosters(league_id)
    players = sc.get_all_players()
    trending = sc.get_trending_adds()

    my_roster = recommender.find_my_roster(rosters, user_id)
    if my_roster is None:
        return render_template(
            "index.html", error="Couldn't find your roster in that league."
        )

    rostered_ids = recommender.rostered_player_ids(rosters)
    free_agents = recommender.free_agents_from_trending(trending, rostered_ids, players)
    bench = recommender.bench_context(my_roster, players)
    bench_groups = recommender.group_by_position(bench)
    recs = recommender.generate_recommendations(free_agents, bench)
    handcuffs = recommender.find_handcuff_pickups(players, rostered_ids)
    questionable = recommender.find_questionable_insurance(players, rostered_ids)

    return render_template(
        "results.html",
        league_name=league.get("name"),
        username=username,
        recs=recs,
        handcuffs=handcuffs,
        questionable=questionable,
        bench=bench,
        bench_groups=bench_groups,
        generated_at=datetime.now().strftime("%A, %B %d %Y"),
    )


if __name__ == "__main__":
    app.run(debug=True)
