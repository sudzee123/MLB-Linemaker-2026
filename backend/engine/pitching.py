"""
Step 3: Recalculated Runs Allowed Per Game

Blends starting pitcher ERA (for their average innings) with bullpen ERA
(for the remaining innings) to produce a single expected RA/G for the
game, given a specific starter.

Formula (from architecture):
  d = SP_IP / SP_GS                           # avg innings per start
  starter_contribution = (SP_ERA / 9) × d
  bullpen_contribution  = (BP_ERA / 9) × (9 - d)
  recalc_RA = starter_contribution + bullpen_contribution

Bullpen ERA is derived from team totals minus all starters' totals.
"""

import logging

from backend.fetchers.mlb_stats import (
    fetch_pitcher_logs,
    fetch_team_pitching,
)

log = logging.getLogger(__name__)

# Fallback ERA values when data is unavailable
DEFAULT_SP_ERA = 4.50
DEFAULT_BP_ERA = 4.20
DEFAULT_IP_PER_GS = 5.0


def calc_recalculated_runs_allowed(
    team_id: int,
    starter_pitcher_id: int | None,
    through_date: str = None,
    start_date: str = None,
) -> dict:
    """
    Compute blended runs-allowed-per-game for a team given their starter.

    Args:
        team_id: MLB team ID
        starter_pitcher_id: MLB player ID of the probable starter (or None if TBD)
        through_date: 'YYYY-MM-DD' cutoff for stat accumulation

    Returns:
        {
          sp_era, sp_ip_per_gs, sp_gs,
          bp_era,
          recalc_ra,
          starter_contribution, bullpen_contribution,
        }
    """
    # ── Starter stats ──────────────────────────────────────────────
    if starter_pitcher_id:
        sp_stats = fetch_pitcher_logs(starter_pitcher_id, through_date, start_date)
    else:
        sp_stats = {}

    sp_gs = sp_stats.get("gs", 0)
    has_real_data = sp_stats.get("ip", 0) > 0

    if sp_gs > 0:
        sp_era = sp_stats["era"]
        sp_ip_per_gs = sp_stats["ip_per_gs"]
    elif has_real_data:
        # Reliever spot-starting: use actual ERA and capped IP estimate
        sp_era = sp_stats["era"]
        sp_ip_per_gs = sp_stats["ip_per_gs"]
        log.info(f"Starter {starter_pitcher_id} is a reliever — using relief ERA={sp_era}, IP/GS={sp_ip_per_gs}")
    else:
        sp_era = DEFAULT_SP_ERA
        sp_ip_per_gs = DEFAULT_IP_PER_GS
        log.info(f"Starter {starter_pitcher_id} has no appearances — using defaults "
                 f"(ERA={DEFAULT_SP_ERA}, IP/GS={DEFAULT_IP_PER_GS})")

    # ── Bullpen ERA derivation ─────────────────────────────────────
    bp_era = _derive_bullpen_era(team_id, starter_pitcher_id, through_date, start_date)

    # ── Blended recalculated RA ───────────────────────────────────
    d = sp_ip_per_gs
    starter_contribution = (sp_era / 9) * d
    bullpen_contribution = (bp_era / 9) * (9 - d)
    recalc_ra = round(starter_contribution + bullpen_contribution, 3)

    return {
        "sp_era": round(sp_era, 2),
        "sp_ip_per_gs": round(sp_ip_per_gs, 2),
        "sp_gs": sp_gs,
        "bp_era": round(bp_era, 2),
        "starter_contribution": round(starter_contribution, 3),
        "bullpen_contribution": round(bullpen_contribution, 3),
        "recalc_ra": recalc_ra,
    }


def _derive_bullpen_era(
    team_id: int,
    starter_pitcher_id: int | None,
    through_date: str = None,
    start_date: str = None,
) -> float:
    """
    Derive bullpen ERA by subtracting starter totals from team pitching totals.

    If we can't isolate the bullpen (missing data), falls back to DEFAULT_BP_ERA.
    """
    team_pit = fetch_team_pitching(team_id, through_date, start_date)
    if not team_pit or not team_pit.get("ip"):
        log.warning(f"No team pitching data for team {team_id} — using default BP ERA")
        return DEFAULT_BP_ERA

    team_ip = team_pit["ip"]
    team_er = team_pit["er"]

    # Starter contribution to team totals
    # We only have the current game's starter — as a simplification for early season,
    # we estimate starter share using league-average ratios (~60% of IP from starters).
    # A more precise approach would require fetching all pitchers' logs; we defer that
    # to a future enhancement and use the team-level ERA adjusted by known SP ERA.
    if starter_pitcher_id:
        sp_stats = fetch_pitcher_logs(starter_pitcher_id, through_date, start_date)
        sp_ip = sp_stats.get("ip", 0)
        sp_er = sp_stats.get("er", 0)
    else:
        sp_ip, sp_er = 0, 0

    bp_ip = team_ip - sp_ip
    bp_er = team_er - sp_er

    if bp_ip <= 0:
        log.warning(f"Team {team_id}: BP IP <= 0 after subtracting starter — using default")
        return DEFAULT_BP_ERA

    bp_era = round((bp_er / bp_ip) * 9, 2)

    # Sanity check: BP ERA should be in plausible range
    if not (1.0 <= bp_era <= 9.0):
        log.warning(f"Team {team_id}: derived BP ERA {bp_era} out of range — using default")
        return DEFAULT_BP_ERA

    return bp_era
