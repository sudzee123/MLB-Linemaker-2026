"""
Step 5: Win Probability and Moneyline Conversion

Architecture formulas:
  kk = ff²   (away expected runs squared)
  zz = nn²   (home expected runs squared)
  ee = kk + zz
  away_win_prob = kk / ee
  home_win_prob = zz / ee

Moneyline conversions:
  prob → moneyline (fair line)
  moneyline → implied probability (for edge calc)
"""


def calc_win_probability(away_exp_r: float, home_exp_r: float) -> dict:
    """
    Convert expected runs into win probabilities via Pythagorean expectation.

    Args:
        away_exp_r: expected runs for the away team
        home_exp_r: expected runs for the home team

    Returns:
        {away_win_prob, home_win_prob, away_fair_ml, home_fair_ml}
    """
    kk = away_exp_r ** 2
    zz = home_exp_r ** 2
    ee = kk + zz

    if ee == 0:
        away_win_prob = 0.5
        home_win_prob = 0.5
    else:
        away_win_prob = kk / ee
        home_win_prob = zz / ee

    return {
        "away_win_prob": round(away_win_prob, 4),
        "home_win_prob": round(home_win_prob, 4),
        "away_fair_ml": prob_to_moneyline(away_win_prob),
        "home_fair_ml": prob_to_moneyline(home_win_prob),
    }


def prob_to_moneyline(prob: float) -> int:
    """
    Convert a win probability to an American moneyline.
    0.60 → -150,  0.40 → +150
    """
    if prob <= 0 or prob >= 1:
        return 0
    if prob >= 0.5:
        return round(-(prob / (1 - prob)) * 100)
    return round(((1 - prob) / prob) * 100)


def moneyline_to_prob(line: int | float) -> float:
    """
    Convert an American moneyline to implied probability.
    -150 → 0.6,  +130 → 0.4348
    """
    if line is None or line == 0:
        return 0.5
    if line < 0:
        return abs(line) / (abs(line) + 100)
    return 100 / (line + 100)
