"""
The Odds API — historical snapshot fetcher for date-range backfill.

Endpoint: GET /v4/historical/sports/baseball_mlb/odds/
Snapshot time: 02:00 UTC on game day (= 9 PM CT the prior evening).

NOTE: Each historical request costs 10 API credits (vs 1 for live).
"""

import logging
from zoneinfo import ZoneInfo

import httpx

from backend.config import ODDS_API_KEY, ODDS_API_BASE

log = logging.getLogger(__name__)

CENTRAL = ZoneInfo("America/Chicago")

REF_PRIORITY = ["pinnacle", "draftkings", "fanduel", "betmgm", "williamhill_us"]


def fetch_historical_odds(snapshot_timestamp: str) -> list[dict]:
    """
    Pull a historical MLB h2h moneyline snapshot from The Odds API.

    Args:
        snapshot_timestamp: ISO 8601 UTC string, e.g. "2026-07-09T02:00:00Z"

    Returns:
        List of game dicts matching the schema of live fetch_odds:
          away_team, home_team, commence_time_utc,
          ref_away_ml, ref_home_ml, ref_book,
          best_away_ml, best_away_book,
          best_home_ml, best_home_book,
          all_away_lines, all_home_lines, num_books
    """
    if not ODDS_API_KEY or ODDS_API_KEY == "your_key_here":
        log.warning("ODDS_API_KEY not set — skipping historical odds fetch")
        return []

    url = f"{ODDS_API_BASE}/historical/sports/baseball_mlb/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "h2h",
        "oddsFormat": "american",
        "date": snapshot_timestamp,
    }

    log.info(f"Fetching historical odds snapshot at {snapshot_timestamp}...")
    try:
        resp = httpx.get(url, params=params, timeout=20)
        resp.raise_for_status()
        wrapper = resp.json()
    except Exception as e:
        log.error(f"Historical odds fetch failed for {snapshot_timestamp}: {e}")
        return []

    remaining = resp.headers.get("x-requests-remaining", "?")
    log.info(f"Historical odds: {remaining} credits remaining after this call")

    events = wrapper.get("data", [])
    if not events:
        log.info(f"No events in historical snapshot for {snapshot_timestamp}")
        return []

    games = []
    for event in events:
        away_team = event.get("away_team", "")
        home_team = event.get("home_team", "")
        commence_utc = event.get("commence_time", "")

        away_lines, home_lines, book_details = [], [], []
        per_book: dict[str, dict] = {}

        for bm in event.get("bookmakers", []):
            bm_key = bm.get("key", "")
            book_title = bm.get("title", bm_key or "Unknown")
            bm_away, bm_home = None, None
            for market in bm.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                for outcome in market.get("outcomes", []):
                    price = outcome.get("price", 0)
                    name = outcome.get("name", "")
                    if name == away_team:
                        away_lines.append(price)
                        book_details.append({"book": book_title, "team": "away", "line": price})
                        bm_away = price
                    elif name == home_team:
                        home_lines.append(price)
                        book_details.append({"book": book_title, "team": "home", "line": price})
                        bm_home = price
            if bm_away is not None and bm_home is not None:
                per_book[bm_key] = {"away": bm_away, "home": bm_home, "title": book_title}

        # Select highest-priority book that priced both sides
        ref_away_ml = ref_home_ml = ref_book = None
        for key in REF_PRIORITY:
            if key in per_book:
                ref_away_ml = per_book[key]["away"]
                ref_home_ml = per_book[key]["home"]
                ref_book = per_book[key]["title"]
                break

        best_away = max(away_lines) if away_lines else None
        best_home = max(home_lines) if home_lines else None

        games.append({
            "away_team": away_team,
            "home_team": home_team,
            "commence_time_utc": commence_utc,
            "ref_away_ml": ref_away_ml,
            "ref_home_ml": ref_home_ml,
            "ref_book": ref_book,
            "best_away_ml": best_away,
            "best_away_book": next(
                (bd["book"] for bd in book_details if bd["team"] == "away" and bd["line"] == best_away), ""
            ),
            "best_home_ml": best_home,
            "best_home_book": next(
                (bd["book"] for bd in book_details if bd["team"] == "home" and bd["line"] == best_home), ""
            ),
            "all_away_lines": sorted(away_lines, reverse=True)[:5],
            "all_home_lines": sorted(home_lines, reverse=True)[:5],
            "num_books": len(event.get("bookmakers", [])),
        })

    log.info(f"Loaded {len(games)} historical games for {snapshot_timestamp}")
    return games
