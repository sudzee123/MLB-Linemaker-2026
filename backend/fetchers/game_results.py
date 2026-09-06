"""
MLB Stats API — final score fetcher for automated W/L determination.

Used in the 2025 historical version to auto-settle tracked plays
without requiring manual user input.
"""

import logging

import httpx

from backend.config import MLB_API_BASE

log = logging.getLogger(__name__)


def fetch_game_result(game_id: int, side: str) -> str | None:
    """
    Fetch the final result for a completed game and return W or L for the given side.

    Args:
        game_id: MLB gamePk
        side:    'home' or 'away' — which side the tracked bet is on

    Returns:
        'W' or 'L' if game is final, None if game not yet finished or on error.
    """
    url = f"{MLB_API_BASE}/schedule"
    params = {"gamePk": game_id, "hydrate": "linescore"}

    try:
        resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.error(f"fetch_game_result({game_id}) failed: {e}")
        return None

    for date_block in data.get("dates", []):
        for game in date_block.get("games", []):
            if game.get("gamePk") != game_id:
                continue

            status = game.get("status", {}).get("abstractGameState", "")
            if status != "Final":
                log.info(f"Game {game_id} is not final (state: {status!r})")
                return None

            linescore = game.get("linescore", {})
            teams = linescore.get("teams", {})
            home_runs = teams.get("home", {}).get("runs", 0) or 0
            away_runs = teams.get("away", {}).get("runs", 0) or 0

            if home_runs == away_runs:
                log.warning(f"Game {game_id} final but tied? home={home_runs} away={away_runs}")
                return None

            if side == "home":
                return "W" if home_runs > away_runs else "L"
            else:
                return "W" if away_runs > home_runs else "L"

    log.warning(f"Game {game_id} not found in schedule response")
    return None
