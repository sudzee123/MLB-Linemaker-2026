"""
CLV live capture (going forward). Ported from the NHL Linemaker.

Two phases:
  1. record_detection() — at track time, lock the bet price as a 'pending' row.
  2. capture_tick() — every 5 min, fill the closing price for pending plays whose
     game is at/near first pitch, via one batched live Odds API call.
"""

import logging
from datetime import datetime, timedelta, timezone

from backend import db
from backend.fetchers.odds import fetch_odds
from backend.clv.math import implied, close_fair_prob, clv

log = logging.getLogger(__name__)

LEAD_MIN = 6
GRACE_MIN = 10


def record_detection(play_id: int, play: dict):
    """Lock the bet price at track time as a pending CLV row. Never raises."""
    try:
        bet_ml = play.get("book_ml")
        commence = play.get("commence_time") or play.get("game_time_utc")
        db.save_clv_row({
            "play_id": play_id,
            "window": play.get("window"),
            "model_prob": play.get("model_prob"),
            "bet_ml": bet_ml,
            "bet_prob": implied(bet_ml) if bet_ml else None,
            "commence_time": commence,
            "source": "live",
            "status": "pending",
        })
    except Exception as e:
        log.warning(f"CLV record_detection failed for play {play_id}: {e}")
        try:
            db.save_clv_row({"play_id": play_id, "source": "live", "status": "missing"})
        except Exception:
            pass


def capture_tick():
    """Fill closing prices for pending plays now at/near first pitch."""
    from backend.main import _resolve_abbrev  # late import — avoids circular

    pending = db.load_clv_pending()
    if not pending:
        return
    now = datetime.now(timezone.utc)

    due = []
    for row in pending:
        ct = row.get("commence_time")
        if not ct:
            continue
        try:
            cdt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
        except Exception:
            continue
        if cdt - timedelta(minutes=LEAD_MIN) <= now <= cdt + timedelta(minutes=GRACE_MIN):
            due.append(row)
        elif now > cdt + timedelta(hours=4):
            db.mark_clv_status(row["id"], "missing")  # window passed, never captured

    if not due:
        return

    events = fetch_odds()
    idx = {}
    for ev in events:
        aab = _resolve_abbrev(ev.get("away_team", ""))
        hab = _resolve_abbrev(ev.get("home_team", ""))
        if aab and hab:
            idx[(aab, hab)] = ev

    for row in due:
        play = db.get_tracked_play(row["play_id"])
        if not play:
            continue
        if play["side"] == "away":
            away_ab, home_ab = play["team_abbrev"], play["opponent_abbrev"]
        else:
            away_ab, home_ab = play["opponent_abbrev"], play["team_abbrev"]
        ev = idx.get((away_ab, home_ab))
        if not ev or ev.get("best_away_ml") is None or ev.get("best_home_ml") is None:
            continue  # leave pending; next tick or the 4h sweep resolves it
        if play["side"] == "away":
            cs, co = ev["best_away_ml"], ev["best_home_ml"]
        else:
            cs, co = ev["best_home_ml"], ev["best_away_ml"]
        cps, cpo = implied(cs), implied(co)
        cf = close_fair_prob(cps, cpo)
        bp = row.get("bet_prob") if row.get("bet_prob") is not None else implied(row["bet_ml"])
        db.update_clv_close(row["id"], {
            "close_ml_side": cs, "close_ml_opp": co, "book": "best(us,us2)",
            "close_prob_side": cps, "close_prob_opp": cpo, "close_fair_prob": cf,
            "clv": clv(cf, bp),
        }, status="ok")
        log.info(f"CLV captured live for play {row['play_id']}: clv={clv(cf, bp):+.4f}")
