"""
Step 4: Offensive Strength Factors

Normalizes each team's RS/G against home/away league averages to produce
dimensionless offense and defense rate factors, which the probability
engine then cross-multiplies to get expected runs for each side.

Architecture formulas:
  xx = away_team_RS_per_game / league_avg_away_RS   (away offense)
  bb = home_team_recalc_RA   / league_avg_home_RA   (home defense leakage)
  aa = home_team_RS_per_game / league_avg_home_RS   (home offense)
  yy = away_team_recalc_RA   / league_avg_away_RA   (away defense leakage)

Expected runs:
  ff (away) = xx * bb * league_avg_away_RS
  nn (home) = aa * yy * league_avg_home_RS
"""


def calc_offensive_strength(
    away_rs_pg: float,
    home_rs_pg: float,
    away_recalc_ra: float,
    home_recalc_ra: float,
    league_avgs: dict,
) -> dict:
    """
    Compute expected runs for each team in a matchup.

    Args:
        away_rs_pg:     away team's season RS/G
        home_rs_pg:     home team's season RS/G
        away_recalc_ra: away team's blended RA/G (from pitching engine)
        home_recalc_ra: home team's blended RA/G (from pitching engine)
        league_avgs:    {home_rs_pg, away_rs_pg} from fetch_league_averages

    Returns:
        {
          xx, bb, aa, yy,          # the four rate factors
          away_exp_r, home_exp_r,  # expected runs per game
        }
    """
    lg_away_rs = league_avgs.get("away_rs_pg", 4.3)
    lg_home_rs = league_avgs.get("home_rs_pg", 4.6)

    # Away team offense vs league away average
    xx = away_rs_pg / lg_away_rs if lg_away_rs else 1.0

    # Home team defense: how leaky relative to league home RA
    # League home RA ≈ league away RS (what visiting teams score at home parks)
    bb = home_recalc_ra / lg_away_rs if lg_away_rs else 1.0

    # Home team offense vs league home average
    aa = home_rs_pg / lg_home_rs if lg_home_rs else 1.0

    # Away team defense: how leaky relative to league away RA
    # League away RA ≈ league home RS (what home teams score)
    yy = away_recalc_ra / lg_home_rs if lg_home_rs else 1.0

    # Expected runs
    away_exp_r = xx * bb * lg_away_rs
    home_exp_r = aa * yy * lg_home_rs

    return {
        "xx": round(xx, 4),
        "bb": round(bb, 4),
        "aa": round(aa, 4),
        "yy": round(yy, 4),
        "away_exp_r": round(away_exp_r, 3),
        "home_exp_r": round(home_exp_r, 3),
    }
