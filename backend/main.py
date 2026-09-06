"""
MLB Linemaker — FastAPI backend
Endpoints:
  GET /api/games?date=YYYY-MM-DD[&through_date=YYYY-MM-DD]
  GET /api/game/{game_id}?date=YYYY-MM-DD
  GET /api/edges?date=YYYY-MM-DD
  GET /api/refresh?date=YYYY-MM-DD&through_date=YYYY-MM-DD
"""

import logging
import os
import threading
import time
from datetime import date as date_type, datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend import db
from backend.models import PlayResultIn, PlayResultUpdate, SettleGroupIn
from backend.scheduler import setup_scheduler
from backend.fetchers.schedule import fetch_schedule, TEAM_ID_TO_ABBREV
from backend.fetchers.mlb_stats import (
    fetch_team_batting,
    fetch_league_averages,
)
from backend.fetchers.odds import fetch_odds
from backend.fetchers.historical_odds import fetch_historical_odds
from backend.fetchers.game_results import fetch_game_result
from backend.engine.pitching import calc_recalculated_runs_allowed
from backend.engine.offense import calc_offensive_strength
from backend.engine.probability import calc_win_probability
from backend.engine.edge import calc_edge

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="MLB Linemaker", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    db.init_db()
    setup_scheduler(_analyze_games)


# ─── Team name → abbreviation resolver ───────────────────────────────────────

_ABBREV_TO_NAME = {
    "LAA": "Los Angeles Angels",    "ARI": "Arizona Diamondbacks",
    "BAL": "Baltimore Orioles",     "BOS": "Boston Red Sox",
    "CHC": "Chicago Cubs",          "CIN": "Cincinnati Reds",
    "CLE": "Cleveland Guardians",   "COL": "Colorado Rockies",
    "DET": "Detroit Tigers",        "HOU": "Houston Astros",
    "KC":  "Kansas City Royals",    "LAD": "Los Angeles Dodgers",
    "WSH": "Washington Nationals",  "NYM": "New York Mets",
    "OAK": "Oakland Athletics",     "PIT": "Pittsburgh Pirates",
    "SD":  "San Diego Padres",      "SEA": "Seattle Mariners",
    "SF":  "San Francisco Giants",  "STL": "St. Louis Cardinals",
    "TB":  "Tampa Bay Rays",        "TEX": "Texas Rangers",
    "TOR": "Toronto Blue Jays",     "MIN": "Minnesota Twins",
    "PHI": "Philadelphia Phillies", "ATL": "Atlanta Braves",
    "CWS": "Chicago White Sox",     "MIA": "Miami Marlins",
    "NYY": "New York Yankees",      "MIL": "Milwaukee Brewers",
}
_NAME_TO_ABBREV = {v: k for k, v in _ABBREV_TO_NAME.items()}
_NAME_TO_ABBREV.update({
    "Kansas City Royals": "KC",
    "Tampa Bay Devil Rays": "TB",
    "Cleveland Indians": "CLE",
    "Los Angeles Angels of Anaheim": "LAA",
    "Las Vegas Athletics": "OAK",
    "Athletics": "OAK",
})


def _resolve_abbrev(team_name: str) -> str | None:
    abbrev = _NAME_TO_ABBREV.get(team_name)
    if abbrev:
        return abbrev
    name_lower = team_name.lower()
    for abbr, full in _ABBREV_TO_NAME.items():
        if any(w in full.lower() for w in name_lower.split() if len(w) > 3):
            return abbr
    return None


# ─── Window helpers ───────────────────────────────────────────────────────────

WINDOWS = ['season', 'l30', 'l21']
_WINDOW_DAYS = {'l30': 30, 'l21': 21}


def _window_start(through_date: str, window: str) -> str | None:
    """Return ISO start date for a rolling window, or None for season."""
    days = _WINDOW_DAYS.get(window)
    if days is None:
        return None
    td = datetime.strptime(through_date, "%Y-%m-%d") - timedelta(days=days)
    return td.strftime("%Y-%m-%d")


def _run_window(
    g: dict,
    through_date: str,
    start_date: str | None,
    league_avgs: dict,
    best_away_ml,
    best_home_ml,
) -> tuple[dict, dict]:
    """Compute win prob / fair ML / edge for both sides under one stat window."""
    away_bat = fetch_team_batting(g["away_team_id"], through_date, start_date)
    home_bat = fetch_team_batting(g["home_team_id"], through_date, start_date)

    away_pit = calc_recalculated_runs_allowed(
        g["away_team_id"], g["away_pitcher_id"], through_date, start_date
    )
    home_pit = calc_recalculated_runs_allowed(
        g["home_team_id"], g["home_pitcher_id"], through_date, start_date
    )

    factors = calc_offensive_strength(
        away_rs_pg=away_bat.get("rs_pg", 0),
        home_rs_pg=home_bat.get("rs_pg", 0),
        away_recalc_ra=away_pit["recalc_ra"],
        home_recalc_ra=home_pit["recalc_ra"],
        league_avgs=league_avgs,
    )
    probs = calc_win_probability(factors["away_exp_r"], factors["home_exp_r"])

    away_edge = calc_edge(probs["away_win_prob"], best_away_ml)
    home_edge = calc_edge(probs["home_win_prob"], best_home_ml)

    away_w = {
        "rs_pg": away_bat.get("rs_pg", 0),
        "games_played": away_bat.get("games", 0),
        "pitcher": {"id": g["away_pitcher_id"], "name": g["away_pitcher_name"], **away_pit},
        "exp_r": factors["away_exp_r"],
        "win_prob": probs["away_win_prob"],
        "fair_ml": probs["away_fair_ml"],
        "book_implied_prob": away_edge["book_implied_prob"],
        "edge": away_edge["edge"],
        "edge_pct": away_edge["edge_pct"],
        "has_edge": away_edge["has_edge"],
    }
    home_w = {
        "rs_pg": home_bat.get("rs_pg", 0),
        "games_played": home_bat.get("games", 0),
        "pitcher": {"id": g["home_pitcher_id"], "name": g["home_pitcher_name"], **home_pit},
        "exp_r": factors["home_exp_r"],
        "win_prob": probs["home_win_prob"],
        "fair_ml": probs["home_fair_ml"],
        "book_implied_prob": home_edge["book_implied_prob"],
        "edge": home_edge["edge"],
        "edge_pct": home_edge["edge_pct"],
        "has_edge": home_edge["has_edge"],
    }
    return away_w, home_w


# ─── Core analysis function ──────────────────────────────────────────────────

def _analyze_games(game_date: str, through_date: str, odds_list: list[dict] | None = None) -> list[dict]:
    cached = db.load_games(game_date, through_date)
    if cached is None:
        cached = _compute_games(game_date, through_date, odds_list)
        db.save_games(game_date, through_date, cached)

    # Auto-track on every call — dedup prevents double-logging
    today = date_type.today().strftime("%Y-%m-%d")
    if game_date >= today:
        _auto_track(cached, game_date)

    return cached


def _compute_games(game_date: str, through_date: str, odds_list: list[dict] | None = None) -> list[dict]:
    schedule = fetch_schedule(game_date)
    if odds_list is None:
        odds_list = fetch_odds(game_date)
    league_avgs = db.load_league_avgs(through_date) or fetch_league_averages(through_date)
    db.save_league_avgs(through_date, league_avgs)

    odds_index: dict[tuple, dict] = {}
    for og in odds_list:
        away_ab = _resolve_abbrev(og["away_team"])
        home_ab = _resolve_abbrev(og["home_team"])
        if away_ab and home_ab:
            odds_index[(away_ab, home_ab)] = og

    results = []
    for g in schedule:
        away_ab = g["away_abbrev"]
        home_ab = g["home_abbrev"]

        og = odds_index.get((away_ab, home_ab))
        if og is None:
            og = _find_odds_fuzzy(away_ab, home_ab, odds_list)

        # Use a single reference book (consistent control variable for edge calc).
        # Fall back to best-per-side only when no priority book is available.
        if og and og.get("ref_away_ml") is not None:
            away_ml = og["ref_away_ml"]
            home_ml = og["ref_home_ml"]
            book_name = og["ref_book"]
        else:
            away_ml = og["best_away_ml"] if og else None
            home_ml = og["best_home_ml"] if og else None
            book_name = og.get("best_away_book", "") if og else ""

        # Compute all three windows
        all_windows = {}
        for wname in WINDOWS:
            wstart = _window_start(through_date, wname)
            aw, hw = _run_window(g, through_date, wstart, league_avgs, away_ml, home_ml)
            all_windows[wname] = {"away": aw, "home": hw}

        season_away = all_windows["season"]["away"]
        season_home = all_windows["season"]["home"]

        # has_edge_any: true if any window has edge for that side
        away_any = any(all_windows[w]["away"]["has_edge"] for w in WINDOWS)
        home_any = any(all_windows[w]["home"]["has_edge"] for w in WINDOWS)

        results.append({
            "game_id": g["game_id"],
            "date": game_date,
            "game_time_ct": g["game_time_ct"],
            "game_time_utc": g["game_time_utc"],
            "num_books": og["num_books"] if og else 0,
            "ref_book": og.get("ref_book") if og else None,
            "league_home_rs_pg": league_avgs.get("home_rs_pg"),
            "league_away_rs_pg": league_avgs.get("away_rs_pg"),
            "away": {
                "team_id": g["away_team_id"],
                "team_name": g["away_team_name"],
                "abbrev": away_ab,
                "book_ml": away_ml,
                "book_name": book_name,
                "has_edge_any": away_any,
                # Season values at top level for backward compat
                **season_away,
                "windows": {w: all_windows[w]["away"] for w in WINDOWS},
            },
            "home": {
                "team_id": g["home_team_id"],
                "team_name": g["home_team_name"],
                "abbrev": home_ab,
                "book_ml": home_ml,
                "book_name": book_name,
                "has_edge_any": home_any,
                **season_home,
                "windows": {w: all_windows[w]["home"] for w in WINDOWS},
            },
        })

    results.sort(key=lambda x: (
        -(x["away"]["has_edge_any"] or x["home"]["has_edge_any"]),
        x["game_time_utc"],
    ))
    return results


def _auto_track(games: list[dict], game_date: str, force: bool = False):
    """Auto-track per window: each window independently triggers when its edge ≥ 1%.
    force=True bypasses the game-time cutoff (used for historical backfill).
    """
    now_utc = datetime.now(timezone.utc)
    for game in games:
        if not force:
            game_time_str = game.get("game_time_utc", "")
            if game_time_str:
                try:
                    game_start = datetime.fromisoformat(game_time_str.replace("Z", "+00:00"))
                    if now_utc >= game_start:
                        continue
                except Exception:
                    pass
        for side_key, opp_key, side_label in [
            ("away", "home", "away"),
            ("home", "away", "home"),
        ]:
            side = game[side_key]
            if side.get("book_ml") is None:
                continue

            opp_abbrev = game[opp_key]["abbrev"]
            book_ml = side["book_ml"]
            book_name = side.get("book_name", "")
            team_name = side["team_name"]
            team_abbrev = side["abbrev"]

            for wname in WINDOWS:
                w = side["windows"][wname]
                edge = w.get("edge")
                if edge is None or edge < 0.01:
                    continue
                # If opponent also has edge in this window, only track the larger edge.
                # Cross-book line selection can make both sides show positive edge;
                # tracking both produces contradictory results for the same game/window.
                opp_w = game[opp_key]["windows"][wname]
                opp_edge = opp_w.get("edge") or 0
                if opp_edge >= 0.01:
                    # Home skips on tie so away is always the tiebreaker winner
                    if side_label == "home" and opp_edge >= edge:
                        continue
                    elif side_label == "away" and opp_edge > edge:
                        continue
                if db.is_auto_tracked(game["game_id"], team_abbrev, wname):
                    continue
                db.save_tracked_play(
                    game_date, game["game_id"], team_abbrev, team_name,
                    opp_abbrev, side_label, book_ml, book_name,
                    w["edge_pct"], window=wname, fair_ml=w["fair_ml"],
                )
                if db.is_opponent_tracked(game["game_id"], opp_abbrev):
                    db.mark_game_conflict(game["game_id"])
                    log.info(
                        f"Conflict flagged game={game['game_id']} "
                        f"{team_abbrev} vs {opp_abbrev} window={wname}"
                    )
                log.info(
                    f"Auto-tracked {team_abbrev} vs {opp_abbrev} "
                    f"window={wname} edge={edge:.1%} book_ml={book_ml}"
                )


def _find_odds_fuzzy(away_ab: str, home_ab: str, odds_list: list[dict]) -> dict | None:
    away_name = _ABBREV_TO_NAME.get(away_ab, "").lower()
    home_name = _ABBREV_TO_NAME.get(home_ab, "").lower()
    for og in odds_list:
        if any(w in og["away_team"].lower() for w in away_name.split() if len(w) > 3):
            if any(w in og["home_team"].lower() for w in home_name.split() if len(w) > 3):
                return og
    return None


# ─── Date helpers ─────────────────────────────────────────────────────────────

def _today() -> str:
    return date_type.today().strftime("%Y-%m-%d")


def _yesterday() -> str:
    return (date_type.today() - timedelta(days=1)).strftime("%Y-%m-%d")


# ─── Game endpoints ───────────────────────────────────────────────────────────

@app.get("/api/games")
def get_games(
    date: str = Query(default=None),
    through_date: str = Query(default=None),
    force_refresh: bool = Query(default=False),
):
    game_date = date or _today()
    stat_date = through_date or _yesterday()
    if force_refresh:
        db.clear_games(game_date, stat_date)
    return _analyze_games(game_date, stat_date)


@app.get("/api/game/{game_id}")
def get_game(
    game_id: int,
    date: str = Query(default=None),
    through_date: str = Query(default=None),
):
    game_date = date or _today()
    stat_date = through_date or _yesterday()
    games = _analyze_games(game_date, stat_date)
    for g in games:
        if g["game_id"] == game_id:
            return g
    raise HTTPException(status_code=404, detail=f"Game {game_id} not found for {game_date}")


@app.get("/api/edges")
def get_edges(
    date: str = Query(default=None),
    through_date: str = Query(default=None),
):
    game_date = date or _today()
    stat_date = through_date or _yesterday()
    games = _analyze_games(game_date, stat_date)
    return [g for g in games if g["away"]["has_edge_any"] or g["home"]["has_edge_any"]]


@app.get("/api/refresh")
def refresh(
    date: str = Query(default=None),
    through_date: str = Query(default=None),
):
    game_date = date or _today()
    stat_date = through_date or _yesterday()
    db.clear_games(game_date, stat_date)
    games = _analyze_games(game_date, stat_date)
    return {
        "through_date": stat_date,
        "games_analyzed": len(games),
        "message": f"Refreshed {len(games)} games for {game_date} using stats through {stat_date}",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


# ─── Results tracking ─────────────────────────────────────────────────────────

def _calc_units(book_ml: int, result: str) -> float:
    if result == "L":
        return -1.0
    return round(book_ml / 100, 4) if book_ml > 0 else round(100 / abs(book_ml), 4)


@app.post("/api/results")
def add_result(payload: PlayResultIn):
    units = _calc_units(payload.book_ml, payload.result)
    result_id = db.save_result(
        payload.game_date, payload.game_id, payload.team_abbrev,
        payload.opponent_abbrev, payload.book_ml, payload.edge_pct,
        payload.result, units, payload.window,
    )
    return {"id": result_id, "units_gained": units}


@app.get("/api/results/summary")
def get_results_summary(
    window: str = Query(default="season", description="Stat window: season | l30 | l21"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    min_edge: float | None = Query(default=None),
    max_edge: float | None = Query(default=None),
    ml_min: int | None = Query(default=None),
    ml_max: int | None = Query(default=None),
    team: str | None = Query(default=None),
    prev_loss_filter: bool = Query(default=False),
):
    results = db.load_results(window, start_date, end_date, min_edge, max_edge, ml_min, ml_max, team, prev_loss_filter)
    wins = sum(1 for r in results if r["result"] == "W")
    losses = len(results) - wins
    net_units = sum(r["units_gained"] for r in results)
    roi_pct = (net_units / len(results) * 100) if results else 0.0

    cumulative = 0.0
    chart_data = []
    for i, r in enumerate(results, 1):
        cumulative += r["units_gained"]
        chart_data.append({
            "id": r["id"],
            "play_num": i,
            "date": r["game_date"],
            "team": r["team_abbrev"],
            "opponent": r["opponent_abbrev"],
            "window": r["window"],
            "book_ml": r["book_ml"],
            "edge_pct": r["edge_pct"],
            "result": r["result"],
            "units": round(r["units_gained"], 3),
            "cumulative_units": round(cumulative, 3),
        })

    return {
        "wins": wins,
        "losses": losses,
        "total_plays": len(results),
        "net_units": round(net_units, 3),
        "roi_pct": round(roi_pct, 1),
        "chart_data": chart_data,
    }


@app.put("/api/results/{result_id}")
def update_result(result_id: int, payload: PlayResultUpdate):
    units = _calc_units(payload.book_ml, payload.result)
    updated = db.update_result(result_id, payload.result, payload.book_ml, payload.edge_pct, units)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Result {result_id} not found")
    return {"units_gained": units}


@app.delete("/api/results/{result_id}")
def delete_result(result_id: int):
    deleted = db.delete_result(result_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Result {result_id} not found")
    return {"deleted": True}


# ─── Tracked plays ────────────────────────────────────────────────────────────

@app.get("/api/plays")
def get_plays():
    return db.load_tracked_plays(settled=False)


@app.get("/api/discrepancies")
def get_discrepancies():
    return db.load_discrepancies()


# ─── Date-range backfill ──────────────────────────────────────────────────────

class BackfillDatesIn(BaseModel):
    start_date: str
    end_date: str

_backfill_status: dict = {"state": "idle", "processed": 0, "total": 0,
                          "current_date": "", "credits_used": 0, "error": ""}
_backfill_thread: threading.Thread | None = None


def _run_backfill_dates(start_date: str, end_date: str):
    global _backfill_status
    start = date_type.fromisoformat(start_date)
    end = date_type.fromisoformat(end_date)

    all_dates = []
    d = start
    while d <= end:
        all_dates.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)

    total = len(all_dates)
    credits_used = 0
    _backfill_status.update({"state": "running", "processed": 0, "total": total,
                              "current_date": "", "credits_used": 0, "error": ""})
    log.info(f"Backfill: {total} dates to process ({start_date} → {end_date})")

    for i, date_str in enumerate(all_dates):
        try:
            _backfill_status["current_date"] = date_str
            through_date = (date_type.fromisoformat(date_str) - timedelta(days=1)).strftime("%Y-%m-%d")

            cached = db.load_games(date_str, through_date)
            if cached is not None:
                # Already computed — just re-run auto_track with force
                _auto_track(cached, date_str, force=True)
                log.info(f"Backfill {date_str}: cache hit, auto-track only")
            else:
                snapshot_ts = f"{date_str}T02:00:00Z"
                hist_odds = fetch_historical_odds(snapshot_ts)
                credits_used += 10
                games = _compute_games(date_str, through_date, hist_odds)
                db.save_games(date_str, through_date, games)
                _auto_track(games, date_str, force=True)
                log.info(f"Backfill {date_str}: {len(games)} games, credits_used={credits_used}")
                time.sleep(0.75)

            _backfill_status.update({"processed": i + 1, "credits_used": credits_used})

        except Exception as e:
            log.error(f"Backfill failed at {date_str}: {e}")
            _backfill_status.update({"state": "error", "error": str(e), "credits_used": credits_used})
            return

    _backfill_status["state"] = "complete"
    log.info(f"Backfill complete — {total} dates, ~{credits_used} credits used")


@app.post("/api/backfill-dates")
def backfill_dates(payload: BackfillDatesIn):
    global _backfill_thread
    if _backfill_thread is not None and _backfill_thread.is_alive():
        return {"message": "Backfill already running", "status": _backfill_status}
    _backfill_thread = threading.Thread(
        target=_run_backfill_dates,
        args=(payload.start_date, payload.end_date),
        daemon=True,
    )
    _backfill_thread.start()
    return {"message": f"Backfill started for {payload.start_date} → {payload.end_date}"}


@app.get("/api/backfill-dates/status")
def backfill_dates_status():
    return _backfill_status


@app.post("/api/plays/auto-settle")
def auto_settle_plays(
    before_date: str = Query(default=None, description="Settle plays for games before this date (default: today)")
):
    """
    For all unsettled tracked_plays for past games, fetch the final score
    from the MLB Stats API and settle them automatically.
    """
    cutoff = before_date or _today()
    plays = db.load_tracked_plays(settled=False)
    past_plays = [p for p in plays if p["game_date"] < cutoff]

    settled_count = 0
    skipped_count = 0
    failed = []

    for play in past_plays:
        result = fetch_game_result(play["game_id"], play["side"])
        if result is None:
            skipped_count += 1
            failed.append({"game_id": play["game_id"], "team": play["team_abbrev"], "reason": "not final or fetch error"})
            continue

        units = _calc_units(play["book_ml"], result)
        try:
            db.save_result(
                play["game_date"], play["game_id"], play["team_abbrev"],
                play["opponent_abbrev"], play["book_ml"], play["edge_pct"],
                result, units, play["window"],
            )
        except Exception:
            pass  # unique constraint — already settled via another window, still mark settled

        db.settle_tracked_play(play["id"])
        settled_count += 1
        log.info(f"Auto-settled {play['team_abbrev']} vs {play['opponent_abbrev']} "
                 f"game={play['game_id']} window={play['window']} → {result}")

    return {
        "settled": settled_count,
        "skipped": skipped_count,
        "failed": failed,
    }


@app.post("/api/results/repair-conflicts")
def repair_conflicts():
    """
    Find conflict pairs where one side has a play_result but the other doesn't,
    then write the inverse result for the missing side.
    """
    incomplete = db.find_incomplete_conflict_pairs()
    created = []
    for row in incomplete:
        inverse = 'L' if row['known_result'] == 'W' else 'W'
        units = _calc_units(row['missing_book_ml'], inverse)
        try:
            result_id = db.save_result(
                row['game_date'], row['game_id'],
                row['missing_team'], row['missing_opponent'],
                row['missing_book_ml'], 'N/A', inverse, units,
                row['missing_window'],
            )
            created.append({
                'id': result_id,
                'game_date': row['game_date'],
                'game_id': row['game_id'],
                'team': row['missing_team'],
                'window': row['missing_window'],
                'result': inverse,
            })
            log.info(
                f"Repair: wrote {row['missing_team']} {row['missing_window']}={inverse} "
                f"(game {row['game_id']}, inverse of {row['known_team']} {row['known_window']}={row['known_result']})"
            )
        except Exception as e:
            log.warning(f"Repair skipped {row['missing_team']} {row['missing_window']} game {row['game_id']}: {e}")

    return {'repaired': len(created), 'entries': created}


@app.get("/api/results/conflict-breakdown")
def get_conflict_breakdown():
    pairs = db.load_conflict_pairs()
    out = {}
    for key, data in pairs.items():
        game_count = data.pop('game_count')
        section = {'game_count': game_count}
        for wname, rows in data.items():
            wins = sum(1 for r in rows if r['result'] == 'W')
            losses = len(rows) - wins
            net = round(sum(r['units_gained'] for r in rows), 3)
            roi = round(net / len(rows) * 100, 1) if rows else 0.0
            cumulative = 0.0
            plays = []
            for i, r in enumerate(rows, 1):
                cumulative += r['units_gained']
                plays.append({
                    'id': r['id'], 'play_num': i, 'date': r['game_date'],
                    'team': r['team_abbrev'], 'opponent': r['opponent_abbrev'],
                    'book_ml': r['book_ml'], 'edge_pct': r['edge_pct'],
                    'result': r['result'], 'units': round(r['units_gained'], 3),
                    'cumulative_units': round(cumulative, 3),
                })
            section[wname] = {
                'wins': wins, 'losses': losses, 'total_plays': len(rows),
                'net_units': net, 'roi_pct': roi, 'plays': plays,
            }
        out[key] = section
    return out


@app.post("/api/plays/settle-group")
def settle_group(payload: SettleGroupIn):
    """Settle all window entries for a game+team at once."""
    plays = db.settle_play_group(payload.game_id, payload.team_abbrev)
    if not plays:
        raise HTTPException(status_code=404, detail="No unsettled plays found")

    result_ids = []
    for play in plays:
        units = _calc_units(play["book_ml"], payload.result)
        result_id = db.save_result(
            play["game_date"], play["game_id"], play["team_abbrev"],
            play["opponent_abbrev"], play["book_ml"], play["edge_pct"],
            payload.result, units, play["window"],
        )
        result_ids.append(result_id)

    return {"result_ids": result_ids, "windows_settled": len(plays)}


@app.delete("/api/plays/group")
def delete_play_group(game_id: int = Query(...), team_abbrev: str = Query(...)):
    deleted = db.delete_play_group(game_id, team_abbrev)
    if not deleted:
        raise HTTPException(status_code=404, detail="No plays found")
    return {"deleted": True}


@app.delete("/api/plays/{play_id}")
def delete_play(play_id: int):
    deleted = db.delete_tracked_play(play_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Play {play_id} not found")
    return {"deleted": True}


# ─── Window backfill ──────────────────────────────────────────────────────────

@app.post("/api/backfill-windows")
def backfill_windows():
    """
    Re-run the model for historical game dates to create L30/L21 play_results
    only where that window independently shows edge ≥ 1%.
    Clears existing L30/L21 data first for a clean rebuild.
    """
    # Clear old L30/L21 data — they were created under the wrong model
    db.delete_window_results('l30')
    db.delete_window_results('l21')
    log.info("Backfill: cleared existing l30/l21 play_results")

    season_results = db.load_results(window='season')
    if not season_results:
        return {"dates_processed": 0, "entries_created": 0, "message": "No season results to backfill"}

    # Nothing pre-exists now — start fresh
    existing: dict[str, set] = {'l30': set(), 'l21': set()}

    # Group all season results by game_date for processing
    by_date: dict[str, list] = {}
    for r in season_results:
        by_date.setdefault(r['game_date'], []).append(r)

    dates_processed = 0
    entries_created = 0

    for game_date in sorted(by_date.keys()):
        results_for_date = by_date[game_date]
        through_date = (
            datetime.strptime(game_date, "%Y-%m-%d") - timedelta(days=1)
        ).strftime("%Y-%m-%d")

        schedule = fetch_schedule(game_date)
        sched_by_id = {g['game_id']: g for g in schedule}

        league_avgs = db.load_league_avgs(through_date)
        if league_avgs is None:
            league_avgs = fetch_league_averages(through_date)
            if league_avgs:
                db.save_league_avgs(through_date, league_avgs)
        if not league_avgs:
            log.warning(f"Backfill: no league avgs for {through_date}, skipping {game_date}")
            continue

        dates_processed += 1

        # Group results by game_id and resolve away/home ML from stored values
        by_game: dict[int, dict] = {}
        for r in results_for_date:
            gid = r['game_id']
            if gid not in by_game:
                by_game[gid] = {'away_ml': None, 'home_ml': None, 'results': []}
            g_sched = sched_by_id.get(gid)
            if g_sched:
                if r['team_abbrev'] == g_sched['away_abbrev']:
                    by_game[gid]['away_ml'] = r['book_ml']
                elif r['team_abbrev'] == g_sched['home_abbrev']:
                    by_game[gid]['home_ml'] = r['book_ml']
            by_game[gid]['results'].append(r)

        for game_id, game_data in by_game.items():
            g = sched_by_id.get(game_id)
            if g is None:
                log.warning(f"Backfill: game_id {game_id} not in {game_date} schedule")
                continue

            for wname in ('l30', 'l21'):
                to_fill = [
                    r for r in game_data['results']
                    if (r['game_id'], r['team_abbrev']) not in existing[wname]
                ]
                if not to_fill:
                    continue

                wstart = _window_start(through_date, wname)
                try:
                    away_w, home_w = _run_window(
                        g, through_date, wstart, league_avgs,
                        game_data['away_ml'], game_data['home_ml'],
                    )
                except Exception as e:
                    log.error(f"Backfill {wname} error game {game_id} on {game_date}: {e}")
                    continue

                for r in to_fill:
                    if r['team_abbrev'] == g['away_abbrev']:
                        w = away_w
                    elif r['team_abbrev'] == g['home_abbrev']:
                        w = home_w
                    else:
                        log.warning(f"Backfill: {r['team_abbrev']} not found in game {game_id}")
                        continue

                    # Only track this window if it independently showed edge ≥ 1%
                    if not w.get('has_edge'):
                        continue

                    key = (r['game_id'], r['team_abbrev'])
                    if key in existing[wname]:
                        continue

                    db.save_result(
                        r['game_date'], r['game_id'], r['team_abbrev'],
                        r['opponent_abbrev'], r['book_ml'], w['edge_pct'],
                        r['result'], r['units_gained'], wname,
                    )
                    existing[wname].add(key)
                    entries_created += 1

        log.info(f"Backfill: {game_date} done, running total {entries_created} entries")

    return {
        "dates_processed": dates_processed,
        "entries_created": entries_created,
        "message": f"Backfilled {entries_created} entries across {dates_processed} dates",
    }


# ─── Static frontend (production) ────────────────────────────────────────────

_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        return FileResponse(_DIST / "index.html")
