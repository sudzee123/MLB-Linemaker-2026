"""
CLV (Closing Line Value) — pure math. Ported to match the NHL Linemaker exactly.

CLV = (de-vigged closing fair prob of the side we bet) − (implied prob of the
price we bet). Signed decimal in probability space; ×100 for percentage points.
The bet side is vigged (single price); the close side is de-vigged (both prices).
"""


def implied(ml: float) -> float:
    """American moneyline -> implied probability (with vig)."""
    if ml > 0:
        return 100.0 / (ml + 100.0)
    return abs(ml) / (abs(ml) + 100.0)


def close_fair_prob(close_prob_side: float, close_prob_opp: float) -> float:
    """De-vig the two closing implied probs into a fair prob for our side."""
    total = close_prob_side + close_prob_opp
    if total <= 0:
        return 0.0
    return close_prob_side / total


def clv(close_fair: float, bet_prob: float) -> float:
    return close_fair - bet_prob
