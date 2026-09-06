"""
Step 5: Edge Calculation

edge = our_probability - book_implied_probability

Positive = value bet (we give the team better odds than the book does).
Negative = no value.

Both sides are compared independently — the book's vig means their two
sides sum to >100%, but we compare each side on its own merits.
"""

from backend.engine.probability import moneyline_to_prob


def calc_edge(our_prob: float, book_ml: int | float | None) -> dict:
    """
    Compute the edge for one side of a bet.

    Args:
        our_prob:  our model's win probability for this team
        book_ml:   book's American moneyline for this team (best available)

    Returns:
        {
          book_implied_prob,
          edge,          # our_prob - book_implied_prob (signed)
          has_edge,      # True if edge > 0
          edge_pct,      # edge as a percentage string e.g. "+2.3%"
        }
    """
    if book_ml is None:
        return {
            "book_implied_prob": None,
            "edge": None,
            "has_edge": False,
            "edge_pct": "N/A",
        }

    book_implied_prob = moneyline_to_prob(book_ml)
    edge = round(our_prob - book_implied_prob, 4)
    has_edge = edge > 0

    sign = "+" if edge >= 0 else ""
    edge_pct = f"{sign}{edge * 100:.1f}%"

    return {
        "book_implied_prob": round(book_implied_prob, 4),
        "edge": edge,
        "has_edge": has_edge,
        "edge_pct": edge_pct,
    }
