# Waiver Wire Scout (v1 prototype)

An AI-prototyping case study: weekly fantasy football waiver recommendations,
generated from real Sleeper league data and explained in plain language.

## What it does

1. You enter your Sleeper username.
2. It looks up your leagues for the current season and you pick one.
3. It pulls your roster, cross-references Sleeper's trending-add data
   against players not already rostered in your league, and suggests
   pickups with a short explanation and a candidate drop from your bench.

No login or API key needed anywhere -- Sleeper's API is public and
read-only, which is what makes multi-user support possible without
building any auth.

## Setup

```bash
pip install -r requirements.txt
flask --app app run --debug
```

Then open http://127.0.0.1:5000 and enter a Sleeper username.

## Deploying it publicly (Render)

This ships with a `render.yaml` blueprint, so Render can configure the
build and start commands automatically:

```yaml
buildCommand: pip install -r requirements.txt
startCommand: gunicorn app:app --bind 0.0.0.0:$PORT
```

Steps:

1. Push this project to a new GitHub repo (Render deploys from GitHub).
2. Go to [render.com](https://render.com) and sign up (GitHub login works).
3. In the dashboard: **New** &rarr; **Blueprint**, connect your repo. Render
   reads `render.yaml` and pre-fills everything.
4. Click **Apply** / **Create**. First deploy takes a few minutes.
5. Your app goes live at `https://<service-name>.onrender.com`.

**Known limitations of Render's free tier, worth knowing about:**
- The instance spins down after ~15 minutes of no traffic, so the first
  request after a quiet period is slow (cold start) while it spins back up.
- The local disk (including `.cache/players_nfl.json`) is ephemeral and
  resets on every redeploy or restart -- the player dictionary just
  re-fetches automatically, so this doesn't break anything, but it does
  mean the "refresh at most every 24 hours" caching benefit resets more
  often than on a machine you keep running yourself.

## Known v1 limitations (see the build & decision log for the full story)

- **News source**: only Sleeper's own injury_status/depth_chart fields and
  trending-add counts are used. No snap-count/usage-trend data source was
  found that covers individual players (see build log entry on the sports
  data API gap) -- so recommendations lean on injury status, depth chart,
  and trending activity rather than granular usage.
- **Drop-candidate logic** is a simple heuristic (same position, prefer an
  injured bench player) -- not a projections model.
- **FAAB bid sizing** isn't addressed; this league uses FAAB waivers, so a
  real add still requires the user to decide a bid amount manually.
- **Player dictionary caching**: the full Sleeper player file is cached
  locally for 24 hours (`.cache/players_nfl.json`) rather than re-fetched
  per request.

## Project structure

```
app.py              Flask routes
sleeper_client.py    Sleeper API wrapper + player-dictionary caching
recommender.py        Cross-referencing / recommendation logic
templates/            HTML pages
static/style.css      Styling
```
