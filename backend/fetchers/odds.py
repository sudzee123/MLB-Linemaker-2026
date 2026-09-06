"""
Step 6: The Odds API — MLB moneyline fetcher

Endpoint: GET /v4/sports/baseball_mlb/odds
Returns best available moneyline per team across all US books,
plus full per-book breakdown for reference.

UTC game times are converted to Central Time (America/Chicago).
"""

import logging
from zoneinfo import ZoneInfo

import httpx

from backend.config import ODDS_API_KEY, ODDS_API_BASE

log = logging.getLogger(__name__)

CENTRAL = ZoneInfo("America/Chicago")

# Priority order for single-book reference lines. Each entry is
# (canonical_label, [substrings to match against key or title]).
BOOK_PRIORITY = [
    ("Pinnacle",   ["pinnacle"]),
    ("DraftKings", ["draftkings"]),
    ("FanDuel",    ["fanduel"]),
    ("BetMGM",     ["betmgm"]),
    ("Caesars",    ["williamhill_us", "caesars"]),
]


def _canonical_book(key: str, title: str) -> str | None:
    """Return the canonical priority-book label if key or title matches."""
    key_l = key.lower()
    title_l = title.lower()
    for label, aliases in BOOK_PRIORITY:
        if any(a in key_l or a in title_l for a in aliases):
            return label
    return None


def fetch_odds(date_str: str = None) -> list[dict]:
    """
    Pull current MLB h2h moneylines from The Odds API.

    Args:
        date_str: Optional 'YYYY-MM-DD' — used only for logging context.
                  The Odds API returns all upcoming games; we don't filter
                  by date server-side (free tier doesn't support it).

    Returns:
        List of game dicts:
          away_team, home_team, commence_time_utc, commence_time_ct,
          best_away_ml, best_away_book,
          best_home_ml, best_home_book,
          all_away_lines, all_home_lines,
          num_books
    """
    if not ODDS_API_KEY or ODDS_API_KEY == "your_key_here":
        log.warning("ODDS_API_KEY not set — skipping odds fetch")
        return []

    url = f"{ODDS_API_BASE}/sports/baseball_mlb/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us,us2",
        "markets": "h2h",
        "oddsFormat": "american",
    }

    log.info(f"Fetching MLB odds from The Odds API (for {date_str or 'all upcoming'})...")
    try:
        resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.error(f"Odds API fetch failed: {e}")
        return []

    remaining = resp.headers.get("x-requests-remaining", "?")
    log.info(f"Odds API requests remaining: {remaining}")

    games = []
    for event in data:
        away_team = event.get("away_team", "")
        home_team = event.get("home_team", "")
        commence_utc = event.get("commence_time", "")

        # Filter to requested date if provided
        if date_str and commence_utc:
            game_date_ct = _utc_to_ct_date(commence_utc)
            if game_date_ct != date_str:
                continue

        away_lines, home_lines, book_details = [], [], []
        book_sides: dict[str, dict[str, int]] = {}  # canonical label → {away/home: price}
        for bm in event.get("bookmakers", []):
            bm_key = bm.get("key", "")
            book_name = bm.get("title", bm_key or "Unknown")
            canonical = _canonical_book(bm_key, book_name)
            for market in bm.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                for outcome in market.get("outcomes", []):
                    price = outcome.get("price", 0)
                    name = outcome.get("name", "")
                    if name == away_team:
                        away_lines.append(price)
                        book_details.append({"book": book_name, "team": "away", "line": price})
                        if canonical:
                            book_sides.setdefault(canonical, {})["away"] = price
                    elif name == home_team:
                        home_lines.append(price)
                        book_details.append({"book": book_name, "team": "home", "line": price})
                        if canonical:
                            book_sides.setdefault(canonical, {})["home"] = price

        best_away = max(away_lines) if away_lines else None
        best_home = max(home_lines) if home_lines else None

        # Find highest-priority book that priced both sides
        ref_away_ml = ref_home_ml = ref_book = None
        for label, _ in BOOK_PRIORITY:
            sides = book_sides.get(label, {})
            if "away" in sides and "home" in sides:
                ref_away_ml = sides["away"]
                ref_home_ml = sides["home"]
                ref_book = label
                break

        games.append({
            "away_team": away_team,
            "home_team": home_team,
            "commence_time_utc": commence_utc,
            "commence_time_ct": _utc_to_ct_str(commence_utc),
            "best_away_ml": best_away,
            "best_away_book": next(
                (bd["book"] for bd in book_details
                 if bd["team"] == "away" and bd["line"] == best_away), ""
            ),
            "best_home_ml": best_home,
            "best_home_book": next(
                (bd["book"] for bd in book_details
                 if bd["team"] == "home" and bd["line"] == best_home), ""
            ),
            "ref_away_ml": ref_away_ml,
            "ref_home_ml": ref_home_ml,
            "ref_book": ref_book,
            "all_away_lines": sorted(away_lines, reverse=True)[:5],
            "all_home_lines": sorted(home_lines, reverse=True)[:5],
            "num_books": len(event.get("bookmakers", [])),
        })

    log.info(f"Loaded odds for {len(games)} games")
    return games


def _utc_to_ct_str(utc_str: str) -> str:
    """Convert UTC ISO string to 'H:MM AM/PM CDT' Central Time string."""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        dt_ct = dt.astimezone(CENTRAL)
        suffix = "CDT" if dt_ct.dst() else "CST"
        return dt_ct.strftime(f"%-I:%M %p {suffix}")
    except Exception:
        return utc_str


def _utc_to_ct_date(utc_str: str) -> str:
    """Return the Central Time date string 'YYYY-MM-DD' for a UTC ISO string."""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        return dt.astimezone(CENTRAL).strftime("%Y-%m-%d")
    except Exception:
        return ""
