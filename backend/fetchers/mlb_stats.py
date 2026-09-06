"""
MLB Stats API fetchers:
  - fetch_team_batting(team_id, through_date, start_date)  → RS/G and game count
  - fetch_pitcher_logs(pitcher_id, through_date, start_date) → ERA, IP/GS
  - fetch_team_pitching(team_id, through_date, start_date)  → team ERA, total IP/ER
  - fetch_league_averages(through_date)         → home/away RS and RA baselines
"""

import logging

import httpx

from backend.config import MLB_API_BASE, SEASON

log = logging.getLogger(__name__)


# ─── Team Batting ────────────────────────────────────────────────────────────

def fetch_team_batting(team_id: int, through_date: str = None, start_date: str = None) -> dict:
    """
    Returns cumulative batting stats for a team, filtered to a date window.
    start_date / through_date are both inclusive.
    """
    if through_date:
        return _team_batting_via_game_log(team_id, through_date, start_date)

    url = f"{MLB_API_BASE}/teams/{team_id}/stats"
    params = {"stats": "season", "group": "hitting", "season": SEASON}
    try:
        resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        splits = resp.json().get("stats", [{}])[0].get("splits", [])
        if not splits:
            log.warning(f"No batting splits for team {team_id}")
            return {}
        stat = splits[0]["stat"]
        games = stat.get("gamesPlayed", 0)
        runs = stat.get("runs", 0)
        return {
            "games": games,
            "runs": runs,
            "rs_pg": round(runs / games, 3) if games else 0.0,
        }
    except Exception as e:
        log.error(f"fetch_team_batting({team_id}) failed: {e}")
        return {}


def _team_batting_via_game_log(team_id: int, through_date: str, start_date: str = None) -> dict:
    """Aggregate game-by-game batting log within an optional date window."""
    url = f"{MLB_API_BASE}/teams/{team_id}/stats"
    params = {"stats": "gameLog", "group": "hitting", "season": SEASON}
    try:
        resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        splits = resp.json().get("stats", [{}])[0].get("splits", [])
    except Exception as e:
        log.error(f"_team_batting_via_game_log({team_id}) failed: {e}")
        return {}

    total_runs, total_games = 0, 0
    for split in splits:
        game_date = split.get("date", "9999")
        if game_date > through_date:
            continue
        if start_date and game_date < start_date:
            continue
        total_runs += split["stat"].get("runs", 0)
        total_games += 1

    return {
        "games": total_games,
        "runs": total_runs,
        "rs_pg": round(total_runs / total_games, 3) if total_games else 0.0,
    }


# ─── Pitcher Game Logs ───────────────────────────────────────────────────────

def fetch_pitcher_logs(pitcher_id: int, through_date: str = None, start_date: str = None) -> dict:
    """
    Returns pitching stats for a pitcher within an optional date window.
    Filters to starts only (or relief if no starts exist).
    """
    url = f"{MLB_API_BASE}/people/{pitcher_id}/stats"
    params = {"stats": "gameLog", "group": "pitching", "season": SEASON}
    try:
        resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        stats_list = resp.json().get("stats", [])
        splits = stats_list[0].get("splits", []) if stats_list else []
    except Exception as e:
        log.error(f"fetch_pitcher_logs({pitcher_id}) failed: {e}")
        return {}

    total_gs, total_gs_ip_outs, total_gs_er = 0, 0, 0
    total_g, total_rel_ip_outs, total_rel_er = 0, 0, 0

    for split in splits:
        game_date = split.get("date", "9999")
        if through_date and game_date > through_date:
            continue
        if start_date and game_date < start_date:
            continue
        stat = split["stat"]
        ip_outs = _ip_str_to_outs(str(stat.get("inningsPitched", "0")))
        er = stat.get("earnedRuns", 0)
        total_g += 1
        total_rel_ip_outs += ip_outs
        total_rel_er += er
        if stat.get("gamesStarted", 0):
            total_gs += 1
            total_gs_ip_outs += ip_outs
            total_gs_er += er

    if total_gs > 0:
        total_ip = total_gs_ip_outs / 3
        era = round((total_gs_er / total_ip) * 9, 2) if total_ip else 0.0
        ip_per_gs = round(total_ip / total_gs, 2)
        return {
            "gs": total_gs,
            "ip": round(total_ip, 2),
            "er": total_gs_er,
            "era": era,
            "ip_per_gs": ip_per_gs,
            "is_reliever": False,
        }

    # No starts in this window — reliever or no data
    if total_g == 0:
        log.warning(f"Pitcher {pitcher_id} has no appearances through {through_date} (start={start_date})")
        return {"gs": 0, "ip": 0.0, "er": 0, "era": 0.0, "ip_per_gs": 0.0, "is_reliever": True}

    total_ip = total_rel_ip_outs / 3
    era = round((total_rel_er / total_ip) * 9, 2) if total_ip else 0.0
    avg_ip_per_app = round(total_ip / total_g, 2)
    ip_per_gs = round(min(max(avg_ip_per_app, 1.0), 3.0), 2)

    log.info(f"Pitcher {pitcher_id} window start={start_date}: relief ERA={era}, IP/app={avg_ip_per_app}")
    return {
        "gs": 0,
        "ip": round(total_ip, 2),
        "er": total_rel_er,
        "era": era,
        "ip_per_gs": ip_per_gs,
        "is_reliever": True,
    }


# ─── Team Pitching (for bullpen derivation) ──────────────────────────────────

def fetch_team_pitching(team_id: int, through_date: str = None, start_date: str = None) -> dict:
    """Returns pitching totals for a team within an optional date window."""
    if through_date:
        return _team_pitching_via_game_log(team_id, through_date, start_date)

    url = f"{MLB_API_BASE}/teams/{team_id}/stats"
    params = {"stats": "season", "group": "pitching", "season": SEASON}
    try:
        resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        splits = resp.json().get("stats", [{}])[0].get("splits", [])
        if not splits:
            return {}
        stat = splits[0]["stat"]
        ip_outs = _ip_str_to_outs(str(stat.get("inningsPitched", "0")))
        ip = ip_outs / 3
        er = stat.get("earnedRuns", 0)
        era = round((er / ip) * 9, 2) if ip else 0.0
        return {"ip": round(ip, 2), "er": er, "era": era}
    except Exception as e:
        log.error(f"fetch_team_pitching({team_id}) failed: {e}")
        return {}


def _team_pitching_via_game_log(team_id: int, through_date: str, start_date: str = None) -> dict:
    url = f"{MLB_API_BASE}/teams/{team_id}/stats"
    params = {"stats": "gameLog", "group": "pitching", "season": SEASON}
    try:
        resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        splits = resp.json().get("stats", [{}])[0].get("splits", [])
    except Exception as e:
        log.error(f"_team_pitching_via_game_log({team_id}) failed: {e}")
        return {}

    total_ip_outs, total_er = 0, 0
    for split in splits:
        game_date = split.get("date", "9999")
        if game_date > through_date:
            continue
        if start_date and game_date < start_date:
            continue
        total_er += split["stat"].get("earnedRuns", 0)
        total_ip_outs += _ip_str_to_outs(str(split["stat"].get("inningsPitched", "0")))

    total_ip = total_ip_outs / 3
    era = round((total_er / total_ip) * 9, 2) if total_ip else 0.0
    return {"ip": round(total_ip, 2), "er": total_er, "era": era}


# ─── League Averages ──────────────────────────────────────────────────────────

def fetch_league_averages(through_date: str = None) -> dict:
    """
    Fetch league-wide home and away runs-per-game averages (season totals).
    Used for all windows — intra-season league average variation is small.
    """
    url = f"{MLB_API_BASE}/teams/stats"
    params = {
        "stats": "season",
        "group": "hitting",
        "season": SEASON,
        "sportId": 1,
    }
    try:
        resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        splits = resp.json().get("stats", [{}])[0].get("splits", [])
    except Exception as e:
        log.error(f"fetch_league_averages failed: {e}")
        splits = []

    total_runs, total_games = 0, 0
    for split in splits:
        stat = split.get("stat", {})
        total_runs += stat.get("runs", 0)
        total_games += stat.get("gamesPlayed", 0)

    if not total_games:
        log.warning("Could not compute league averages — using historical defaults")
        return {"home_rs_pg": 4.6, "away_rs_pg": 4.3}

    league_rs_pg = total_runs / total_games
    home_rs_pg = round(league_rs_pg * 1.04, 3)
    away_rs_pg = round(league_rs_pg * 0.96, 3)

    log.info(f"League averages: RS/G={league_rs_pg:.3f}, home={home_rs_pg}, away={away_rs_pg}")
    return {"home_rs_pg": home_rs_pg, "away_rs_pg": away_rs_pg}


# ─── Utility ─────────────────────────────────────────────────────────────────

def _ip_str_to_outs(ip_str: str) -> int:
    """Convert MLB innings-pitched string to total outs. '5.2' → 17 outs."""
    try:
        parts = str(ip_str).split(".")
        full_innings = int(parts[0])
        extra_outs = int(parts[1]) if len(parts) > 1 else 0
        return full_innings * 3 + extra_outs
    except (ValueError, IndexError):
        return 0
