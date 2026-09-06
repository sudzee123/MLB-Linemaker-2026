"""
Fetches today's (or a given date's) MLB schedule with probable pitchers.
Returns structured game data ready for the calculation engine.
"""

import logging
from zoneinfo import ZoneInfo

import httpx

from backend.config import MLB_API_BASE, SEASON, TIMEZONE

log = logging.getLogger(__name__)

CENTRAL = ZoneInfo(TIMEZONE)
UTC = ZoneInfo("UTC")

# Official MLB team ID → abbreviation
TEAM_ID_TO_ABBREV = {
    108: "LAA", 109: "ARI", 110: "BAL", 111: "BOS", 112: "CHC",
    113: "CIN", 114: "CLE", 115: "COL", 116: "DET", 117: "HOU",
    118: "KC",  119: "LAD", 120: "WSH", 121: "NYM", 133: "OAK",
    134: "PIT", 135: "SD",  136: "SEA", 137: "SF",  138: "STL",
    139: "TB",  140: "TEX", 141: "TOR", 142: "MIN", 143: "PHI",
    144: "ATL", 145: "CWS", 146: "MIA", 147: "NYY", 158: "MIL",
}


def fetch_schedule(date_str: str) -> list[dict]:
    """
    Fetch regular-season games for a given date.
    For today/future: only Preview/Scheduled games.
    For past dates: include Final games so results can be logged.

    Args:
        date_str: 'YYYY-MM-DD'

    Returns:
        List of game dicts:
          game_id, away_team_id, away_team_name, away_abbrev,
          home_team_id, home_team_name, home_abbrev,
          game_time_utc, game_time_ct,
          away_pitcher_id, away_pitcher_name,
          home_pitcher_id, home_pitcher_name
    """
    from datetime import date as date_type
    is_past = date_str < date_type.today().strftime("%Y-%m-%d")

    url = f"{MLB_API_BASE}/schedule"
    params = {
        "sportId": 1,
        "date": date_str,
        "season": SEASON,
        "gameType": "R",
        "hydrate": "probablePitcher,team",
    }

    log.info(f"Fetching schedule for {date_str}...")
    try:
        resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.error(f"Schedule fetch failed: {e}")
        return []

    games = []
    for date_block in data.get("dates", []):
        for g in date_block.get("games", []):
            status = g.get("status", {}).get("abstractGameState", "")
            allowed = ("Preview", "Scheduled", "Live", "Final") if is_past else ("Preview", "Scheduled", "Live")
            if status not in allowed:
                continue

            away = g["teams"]["away"]
            home = g["teams"]["home"]

            away_team_id = away["team"]["id"]
            home_team_id = home["team"]["id"]

            # Probable pitchers (may be None early in the week)
            away_pitcher = away.get("probablePitcher") or {}
            home_pitcher = home.get("probablePitcher") or {}

            game_time_utc = g.get("gameDate", "")
            game_time_ct = _utc_to_ct(game_time_utc) if game_time_utc else ""

            games.append({
                "game_id": g["gamePk"],
                "away_team_id": away_team_id,
                "away_team_name": away["team"].get("name", ""),
                "away_abbrev": TEAM_ID_TO_ABBREV.get(away_team_id, "???"),
                "home_team_id": home_team_id,
                "home_team_name": home["team"].get("name", ""),
                "home_abbrev": TEAM_ID_TO_ABBREV.get(home_team_id, "???"),
                "game_time_utc": game_time_utc,
                "game_time_ct": game_time_ct,
                "away_pitcher_id": away_pitcher.get("id"),
                "away_pitcher_name": away_pitcher.get("fullName", "TBD"),
                "home_pitcher_id": home_pitcher.get("id"),
                "home_pitcher_name": home_pitcher.get("fullName", "TBD"),
            })

    log.info(f"Found {len(games)} upcoming games for {date_str}")
    return games


def _utc_to_ct(utc_str: str) -> str:
    """
    Convert a UTC ISO string (e.g. '2026-04-07T18:10:00Z') to a
    human-readable Central Time string (e.g. '1:10 PM CT').
    """
    from datetime import datetime
    try:
        dt_utc = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        dt_ct = dt_utc.astimezone(CENTRAL)
        suffix = "CDT" if dt_ct.dst() else "CST"
        return dt_ct.strftime(f"%-I:%M %p {suffix}")
    except Exception:
        return utc_str
