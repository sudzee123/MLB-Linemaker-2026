# MLB Line Maker — System Architecture

## Overview

An automated MLB handicapping system that replaces a manual Google Sheets workflow. It scrapes/fetches stats, runs probability calculations, compares against sportsbook lines, and surfaces edges via a web dashboard accessible from desktop and mobile.

---

## System Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    DATA SOURCES                         │
│                                                         │
│  MLB Stats API          The Odds API                    │
│  (statsapi.mlb.com)     (api.the-odds-api.com)          │
│  ├─ Team Game Logs      ├─ Moneylines                   │
│  ├─ Pitcher Game Logs   ├─ Game times (UTC)             │
│  ├─ Team Pitching       └─ Bookmaker odds               │
│  ├─ League-wide splits                                  │
│  └─ Bullpen ERA (derived)                               │
└────────────────┬────────────────────┬───────────────────┘
                 │                    │
                 ▼                    ▼
┌─────────────────────────────────────────────────────────┐
│              BACKEND (Python / FastAPI)                  │
│                                                         │
│  1. Data Fetcher Layer                                  │
│     ├─ fetch_team_batting(team, through_date)            │
│     ├─ fetch_pitcher_logs(pitcher, through_date)         │
│     ├─ fetch_team_bullpen_era(team, through_date)        │
│     ├─ fetch_league_averages(through_date)               │
│     └─ fetch_odds(date)                                 │
│                                                         │
│  2. Calculation Engine                                  │
│     ├─ calc_recalculated_runs_allowed(starter, bullpen)  │
│     ├─ calc_offensive_strength(team, league_avgs)        │
│     ├─ calc_win_probability(away, home, league_avgs)     │
│     └─ calc_edge(our_prob, book_prob)                   │
│                                                         │
│  3. API Layer (FastAPI endpoints)                       │
│     ├─ GET /api/games?date=2026-04-07                   │
│     ├─ GET /api/game/{game_id}                          │
│     ├─ GET /api/edges?date=2026-04-07                   │
│     └─ GET /api/refresh?through_date=2026-04-05         │
│                                                         │
│  4. Scheduler (daily auto-refresh)                      │
│     └─ Runs at ~6 AM CT, pulls data through yesterday   │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│           FRONTEND (React Dashboard)                    │
│                                                         │
│  ┌───────────────────────────────────────────────┐      │
│  │  DATE SELECTOR: [◀ Apr 6] [Apr 7 ▶]          │      │
│  │  Data through: Apr 5, 2026                    │      │
│  └───────────────────────────────────────────────┘      │
│                                                         │
│  ┌───────────────────────────────────────────────┐      │
│  │  GAME CARD (one per matchup)                  │      │
│  │                                                │      │
│  │  CHC @ MIL — 1:10 PM CT (Miller Park)         │      │
│  │                                                │      │
│  │  Away: CHC         │  Home: MIL               │      │
│  │  SP: J. Steele     │  SP: F. Peralta          │      │
│  │  SP ERA: 3.12      │  SP ERA: 3.45            │      │
│  │  SP IP/GS: 5.8     │  SP IP/GS: 5.5           │      │
│  │  BP ERA: 3.88      │  BP ERA: 4.12            │      │
│  │  Recalc RA: 3.52   │  Recalc RA: 3.81        │      │
│  │  RS/G: 4.67        │  RS/G: 4.23              │      │
│  │                                                │      │
│  │  ── OUR LINE ──────────────────────────────── │      │
│  │  CHC Win Prob: 54.3%  →  -119                 │      │
│  │  MIL Win Prob: 45.7%  →  +119                 │      │
│  │                                                │      │
│  │  ── BOOK LINE (DraftKings) ───────────────── │      │
│  │  CHC: -130 (implied 56.5%)                    │      │
│  │  MIL: +110 (implied 47.6%)                    │      │
│  │                                                │      │
│  │  ── EDGE ─────────────────────────────────── │      │
│  │  CHC: -2.2% (NO EDGE)                        │      │
│  │  MIL: +2.2% (EDGE ✓)  ← highlighted          │      │
│  │                                                │      │
│  └───────────────────────────────────────────────┘      │
│                                                         │
│  Mobile-responsive, works on iPhone Safari              │
└─────────────────────────────────────────────────────────┘
```

---

## Data Sources — Detailed

### 1. MLB Stats API (statsapi.mlb.com)

Free, no API key required, returns JSON. This is the official MLB data feed.

**Endpoints we use:**

| What We Need | Endpoint | Notes |
|---|---|---|
| Today's schedule | `/api/v1/schedule?date=2026-04-07&sportId=1` | Gets game IDs, teams, probable pitchers |
| Team batting game log | `/api/v1/teams/{teamId}/stats?stats=gameLog&group=hitting&season=2026` | Filter by date range for cumulative R, G |
| Pitcher game log | `/api/v1/people/{playerId}/stats?stats=gameLog&group=pitching&season=2026` | IP, GS, ER → derive ERA |
| Team pitching stats | `/api/v1/teams/{teamId}/stats?stats=season&group=pitching&season=2026` | Team-level pitching for bullpen derivation |
| League-wide splits | `/api/v1/stats?stats=season&group=hitting&sportIds=1&season=2026&splitBy=homeAway` | Home/away RS and RA league averages |
| Probable pitchers | Included in schedule endpoint | Maps starter to game |

**Bullpen ERA derivation:**
- Team total: (Team ER / Team IP) × 9 = Team ERA
- Starters total: Sum of all starters' ER and IP
- Bullpen: (Team ER - Starters ER) / (Team IP - Starters IP) × 9

### 2. The Odds API (api.the-odds-api.com)

Requires API key (you have one). Returns odds in American, decimal, or implied formats.

**Endpoint:**
```
GET /v4/sports/baseball_mlb/odds/?apiKey={key}&regions=us&markets=h2h&oddsFormat=american
```

**Key details:**
- `commence_time` is in UTC → convert to Central (UTC-5 in CDT)
- Returns odds from multiple books — we can pick one (e.g., DraftKings) or show the best available
- Free tier: 500 requests/month. Enough for daily pulls.

---

## Calculation Engine — Step by Step

### Step 1: Recalculated Runs Allowed Per Game (Pitching)

For each team's **starting pitcher in a specific game**:

```
d = SP_IP / SP_GS                          # starter avg innings/start
starter_contribution = (SP_ERA / 9) × d    # runs starter gives up
bullpen_contribution = (BP_ERA / 9) × (9 - d)  # runs pen gives up
recalc_RA = starter_contribution + bullpen_contribution
```

Example: SP ERA 3.60, SP averages 5.2 IP/GS, BP ERA 4.20
```
d = 5.2
starter = (3.60 / 9) × 5.2 = 2.080
bullpen = (4.20 / 9) × (9 - 5.2) = 1.773
recalc_RA = 3.853 runs/game
```

### Step 2: Offensive Strength / Defensive Factors

Using league-wide home/away averages as baselines:

```
# Away team offense factor
xx = away_team_RS_per_game / league_avg_away_RS

# Home team defense factor (using recalc RA from Step 1)
bb = home_team_recalc_RA / league_avg_home_RA

# Home team offense factor
aa = home_team_RS_per_game / league_avg_home_RS

# Away team defense factor
yy = away_team_recalc_RA / league_avg_away_RA
```

### Step 3: Expected Runs & Win Probability

```
# Expected runs for away team
ff = xx × bb × league_avg_away_RS
kk = ff²

# Expected runs for home team
nn = aa × yy × league_avg_home_RS
zz = nn²

# Win probability
ee = kk + zz
if kk > zz:
    away_win_prob = kk / ee    # away team favored
    home_win_prob = zz / ee
else:
    home_win_prob = zz / ee    # home team favored
    away_win_prob = kk / ee
```

### Step 4: Moneyline ↔ Probability Conversion

```python
# Probability → Moneyline
def prob_to_moneyline(prob):
    if prob >= 0.5:
        return round(-(prob / (1 - prob)) * 100)    # negative line
    else:
        return round(((1 - prob) / prob) * 100)      # positive line

# Moneyline → Implied Probability
def moneyline_to_prob(line):
    if line < 0:
        return abs(line) / (abs(line) + 100)
    else:
        return 100 / (line + 100)
```

### Step 5: Edge Calculation

```
edge = our_probability - book_implied_probability
```

- Positive edge = value bet (we think team wins more often than the book does)
- Negative edge = no value

**Note:** The book's implied probabilities from both sides sum to >100% (the vig/juice). We compare each side independently — our prob vs. book's implied prob for that same side.

---

## Project Structure (for Claude Code)

```
mlb-linemaker/
├── backend/
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # API keys, timezone settings
│   ├── fetchers/
│   │   ├── mlb_stats.py        # MLB Stats API calls
│   │   ├── odds.py             # The Odds API calls
│   │   └── schedule.py         # Game schedule + probable pitchers
│   ├── engine/
│   │   ├── pitching.py         # Recalculated runs allowed
│   │   ├── offense.py          # Offensive strength factors
│   │   ├── probability.py      # Win prob + moneyline conversion
│   │   └── edge.py             # Edge calculation
│   ├── models.py               # Data classes / Pydantic models
│   ├── scheduler.py            # Daily auto-refresh logic
│   └── db.py                   # SQLite for caching daily snapshots
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── GameCard.jsx    # Individual matchup display
│   │   │   ├── DatePicker.jsx  # Navigate between game dates
│   │   │   ├── EdgeBadge.jsx   # Visual edge indicator
│   │   │   └── StatsBreakdown.jsx  # Expandable calculation detail
│   │   └── hooks/
│   │       └── useGames.js     # API fetch hooks
│   └── package.json
├── requirements.txt
├── .env                        # ODDS_API_KEY, etc.
└── README.md
```

---

## Timing & Data Freshness Logic

```
Timeline for games on April 7:

April 5 (end of day)     → Games complete, stats finalized
April 6 (6:00 AM CT)     → Scheduler runs:
                             1. Fetches all stats through April 5
                             2. Pulls probable pitchers for April 7
                             3. Runs all calculations
                             4. Pulls available odds for April 7
April 6 (morning)        → Dashboard shows April 7 games with full analysis
April 6 (periodically)   → Odds refresh every ~2 hours as lines move
April 7 (game day)       → Final odds refresh, analysis still available
```

**UTC → Central conversion:**
- CDT (summer): UTC - 5 hours
- CST (winter): UTC - 6 hours
- A game at `2026-04-07T18:10:00Z` = **1:10 PM CT** on April 7
- We use `pytz` or `zoneinfo` with `America/Chicago`

---

## Deployment Path

**Phase 1 — Local (start here)**
- Run backend on localhost:8000, frontend on localhost:3000
- Access from your Mac/PC browser
- iPhone access: same Wi-Fi, use computer's local IP (e.g., 192.168.1.x:3000)

**Phase 2 — Cloud (when ready)**
- Deploy to Railway, Fly.io, or DigitalOcean ($5-6/month)
- Custom domain optional (e.g., lines.yourdomain.com)
- HTTPS, accessible from anywhere on your phone
- Add basic auth so only you can see it

---

## Claude Code Implementation Plan

When you open Claude Code, you'd work through this roughly in order:

1. **Scaffold the project** — directory structure, dependencies, .env
2. **Build the MLB Stats API fetcher** — get schedule, team batting logs, pitcher logs working
3. **Build the bullpen ERA derivation** — team pitching minus starters
4. **Build the league averages fetcher** — home/away splits
5. **Build the calculation engine** — pitching recalc → offense factors → win prob → edge
6. **Wire up The Odds API** — fetch lines, convert UTC times
7. **Create the FastAPI endpoints** — serve calculated data as JSON
8. **Build the React dashboard** — game cards, date picker, edge display
9. **Add the scheduler** — daily auto-refresh via APScheduler or cron
10. **Test with real data** — validate calculations against your existing spreadsheet
11. **Deploy** — push to cloud when satisfied

Each step is a natural Claude Code session. You can validate as you go.
