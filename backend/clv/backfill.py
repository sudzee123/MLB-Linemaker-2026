"""
CLV historical backfill. Ported from the NHL Linemaker.

Buckets settled plays by UTC hour, takes one closing snapshot per bucket at
(earliest game in bucket − 5 min) via the historical Odds API (us,us2 →
20 credits/call), de-vigs the two closing prices, and writes a clv_log row per
play. Snapshots are cached, so re-runs and resumes cost 0 credits.
"""

import time
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import httpx

from backend import db
from backend.config import MLB_API_BASE, SEASON
from backend.fetchers.historical_odds import fetch_historical_odds
from backend.clv.math import implied, close_fair_prob, clv

log = logging.getLogger(__name__)

LEAD_MIN = 5

_state = {"status": "idle", "processed": 0, "total": 0,
          "credits_used": 0, "ok": 0, "missing": 0, "current": ""}


def get_state() -> dict:
    return dict(_state)


def _commence_map(start_date: str, end_date: str) -> dict:
    """game_id -> commence_time (ISO UTC) from the free MLB schedule."""
    try:
        r = httpx.get(f"{MLB_API_BASE}/schedule", params={
            "sportId": 1, "startDate": start_date, "endDate": end_date,
            "season": SEASON, "gameType": "R,F,D,L,W",
        }, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.error(f"CLV commence map fetch failed: {e}")
        return {}
    m = {}
    for date_block in data.get("dates", []):
        for g in date_block.get("games", []):
            m[g["gamePk"]] = g.get("gameDate", "")
    return m


def run_clv_backfill(start_date: str, end_date: str) -> dict:
    from backend.main import _resolve_abbrev  # late import — avoids circular

    plays = db.load_result_rows_for_clv(start_date, end_date)
    db.delete_clv_backfill_for_plays([p["id"] for p in plays])
    commence = _commence_map(start_date, end_date)

    def _miss(p, ct=None):
        db.save_clv_row({
            "play_id": p["id"], "window": p["window"], "bet_ml": p["book_ml"],
            "bet_prob": implied(p["book_ml"]) if p["book_ml"] else None,
            "commence_time": ct, "source": "backfill", "status": "missing",
        })

    buckets = defaultdict(list)
    for p in plays:
        ct = commence.get(p["game_id"])
        if not ct:
            _miss(p)
            continue
        buckets[ct[:13]].append((p, ct))

    _state.update({"status": "running", "total": len(plays), "processed": 0,
                   "credits_used": 0, "ok": 0, "missing": 0, "current": ""})

    for bkey in sorted(buckets):
        items = buckets[bkey]
        earliest = min(ct for _, ct in items)
        try:
            snap_dt = datetime.fromisoformat(earliest.replace("Z", "+00:00"))
        except Exception:
            for p, ct in items:
                _miss(p, ct); _state["processed"] += 1; _state["missing"] += 1
            continue
        snap_ts = (snap_dt - timedelta(minutes=LEAD_MIN)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        events = db.load_clv_snapshot(snap_ts)
        if events is None:
            events = fetch_historical_odds(snap_ts, regions="us,us2")
            db.save_clv_snapshot(snap_ts, events)
            _state["credits_used"] += 20
            time.sleep(0.2)

        idx = {}
        for ev in events:
            aab = _resolve_abbrev(ev.get("away_team", ""))
            hab = _resolve_abbrev(ev.get("home_team", ""))
            if aab and hab:
                idx[(aab, hab)] = ev

        for p, ct in items:
            _state["processed"] += 1
            _state["current"] = p["game_date"]
            if p["side"] == "away":
                away_ab, home_ab = p["team_abbrev"], p["opponent_abbrev"]
            else:
                away_ab, home_ab = p["opponent_abbrev"], p["team_abbrev"]

            ev = idx.get((away_ab, home_ab))
            if not ev or ev.get("best_away_ml") is None or ev.get("best_home_ml") is None:
                _miss(p, ct); _state["missing"] += 1
                continue

            if p["side"] == "away":
                cs, co = ev["best_away_ml"], ev["best_home_ml"]
            else:
                cs, co = ev["best_home_ml"], ev["best_away_ml"]

            bp = implied(p["book_ml"])
            cps, cpo = implied(cs), implied(co)
            cf = close_fair_prob(cps, cpo)
            db.save_clv_row({
                "play_id": p["id"], "window": p["window"], "bet_ml": p["book_ml"], "bet_prob": bp,
                "commence_time": ct, "close_ml_side": cs, "close_ml_opp": co, "book": "best(us,us2)",
                "close_prob_side": cps, "close_prob_opp": cpo, "close_fair_prob": cf, "clv": clv(cf, bp),
                "source": "backfill", "status": "ok",
            })
            _state["ok"] += 1

    _state["status"] = "complete"
    log.info(f"CLV backfill done: {_state['ok']} ok, {_state['missing']} missing, "
             f"~{_state['credits_used']} credits")
    return dict(_state)
