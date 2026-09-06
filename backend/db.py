"""
SQLite cache for daily game analysis snapshots.
Avoids re-fetching all API data on every page load.
Cache is keyed by (date, through_date).
"""

import json
import os
import sqlite3
import logging
from pathlib import Path

log = logging.getLogger(__name__)

DB_PATH = Path(os.environ.get("DB_PATH", str(Path(__file__).parent.parent / "linemaker.db")))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist, and run any needed migrations."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS game_cache (
                date TEXT NOT NULL,
                through_date TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (date, through_date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS league_avg_cache (
                through_date TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS play_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_date TEXT NOT NULL,
                game_id INTEGER NOT NULL,
                team_abbrev TEXT NOT NULL,
                opponent_abbrev TEXT NOT NULL,
                book_ml INTEGER NOT NULL,
                edge_pct TEXT NOT NULL,
                result TEXT NOT NULL,
                units_gained REAL NOT NULL,
                window TEXT NOT NULL DEFAULT 'season',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tracked_plays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_date TEXT NOT NULL,
                game_id INTEGER NOT NULL,
                team_abbrev TEXT NOT NULL,
                team_name TEXT NOT NULL,
                opponent_abbrev TEXT NOT NULL,
                side TEXT NOT NULL,
                book_ml INTEGER NOT NULL,
                book_name TEXT NOT NULL,
                edge_pct TEXT NOT NULL,
                fair_ml INTEGER,
                window TEXT NOT NULL DEFAULT 'season',
                settled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # ── Migrations for existing databases ──────────────────────────
        for col, table, defn in [
            ("window",    "play_results",  "TEXT NOT NULL DEFAULT 'season'"),
            ("window",    "tracked_plays", "TEXT NOT NULL DEFAULT 'season'"),
            ("fair_ml",   "tracked_plays", "INTEGER"),
            ("conflict",  "tracked_plays", "INTEGER NOT NULL DEFAULT 0"),
        ]:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {defn}")
                log.info(f"Migration: added {table}.{col}")
            except Exception:
                pass  # column already exists

        # ── Backfill conflict flag for existing opposing-side plays ────
        try:
            conn.execute("""
                UPDATE tracked_plays SET conflict = 1
                WHERE game_id IN (
                    SELECT DISTINCT a.game_id
                    FROM tracked_plays a
                    JOIN tracked_plays b
                      ON a.game_id = b.game_id
                     AND a.opponent_abbrev = b.team_abbrev
                     AND a.team_abbrev != b.team_abbrev
                )
            """)
        except Exception as e:
            log.warning(f"Conflict backfill warning: {e}")

        # ── Dedup any duplicate (game_id, team_abbrev, window) rows ────
        # Keep the lowest id per combination, remove the rest
        try:
            conn.execute("""
                DELETE FROM play_results
                WHERE id NOT IN (
                    SELECT MIN(id)
                    FROM play_results
                    GROUP BY game_id, team_abbrev, window
                )
            """)
        except Exception as e:
            log.warning(f"Dedup migration warning: {e}")

        # ── Unique index to prevent future duplicates ──────────────────
        try:
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS
                uq_play_results_game_team_window
                ON play_results (game_id, team_abbrev, window)
            """)
        except Exception as e:
            log.warning(f"Unique index warning: {e}")

    log.info(f"DB initialized at {DB_PATH}")


# ─── play_results ──────────────────────────────────────────────────────────────

def save_result(
    game_date: str, game_id: int, team_abbrev: str, opponent_abbrev: str,
    book_ml: int, edge_pct: str, result: str, units_gained: float,
    window: str = 'season',
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO play_results
               (game_date, game_id, team_abbrev, opponent_abbrev,
                book_ml, edge_pct, result, units_gained, window)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (game_date, game_id, team_abbrev, opponent_abbrev,
             book_ml, edge_pct, result, units_gained, window),
        )
        return cur.lastrowid


def load_results(
    window: str = 'season',
    start_date: str | None = None,
    end_date: str | None = None,
    min_edge: float | None = None,
    max_edge: float | None = None,
    ml_min: int | None = None,
    ml_max: int | None = None,
    team: str | None = None,
    prev_loss_filter: bool = False,
) -> list[dict]:
    if window == 'conflicts':
        conditions = ["game_id IN (SELECT DISTINCT game_id FROM tracked_plays WHERE conflict=1)"]
        params = []
    else:
        conditions = ["window = ?"]
        params = [window]
    if start_date:
        conditions.append("game_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("game_date <= ?")
        params.append(end_date)
    if min_edge is not None:
        conditions.append("CAST(REPLACE(REPLACE(edge_pct, '%', ''), '+', '') AS REAL) >= ?")
        params.append(min_edge)
    if max_edge is not None:
        conditions.append("CAST(REPLACE(REPLACE(edge_pct, '%', ''), '+', '') AS REAL) <= ?")
        params.append(max_edge)
    if ml_min is not None:
        conditions.append("book_ml >= ?")
        params.append(ml_min)
    if ml_max is not None:
        conditions.append("book_ml <= ?")
        params.append(ml_max)
    if team:
        conditions.append("UPPER(team_abbrev) LIKE UPPER(?)")
        params.append(f'%{team}%')
    if prev_loss_filter:
        # Include only plays where the immediately preceding series game (same
        # team vs same opponent, within 5 days, same window) was a loss with
        # edge ≤ 10% and ML ≥ -109.
        conditions.append("""
            EXISTS (
                SELECT 1 FROM play_results prev
                WHERE prev.team_abbrev    = play_results.team_abbrev
                  AND prev.opponent_abbrev = play_results.opponent_abbrev
                  AND prev.window          = play_results.window
                  AND prev.result          = 'L'
                  AND prev.book_ml        >= -109
                  AND CAST(REPLACE(REPLACE(prev.edge_pct, '%', ''), '+', '') AS REAL) <= 10.0
                  AND prev.game_date = (
                      SELECT MAX(p2.game_date)
                      FROM play_results p2
                      WHERE p2.team_abbrev     = play_results.team_abbrev
                        AND p2.opponent_abbrev  = play_results.opponent_abbrev
                        AND p2.window           = play_results.window
                        AND p2.game_date        < play_results.game_date
                  )
                  AND julianday(play_results.game_date) - julianday(prev.game_date) <= 5
            )
        """)
    where = f" WHERE {' AND '.join(conditions)}"
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM play_results{where} ORDER BY game_date ASC, id ASC",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def update_result(result_id: int, result: str, book_ml: int, edge_pct: str, units_gained: float) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            """UPDATE play_results
               SET result=?, book_ml=?, edge_pct=?, units_gained=?
               WHERE id=?""",
            (result, book_ml, edge_pct, units_gained, result_id),
        )
        return cur.rowcount > 0


def delete_result(result_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM play_results WHERE id=?", (result_id,))
        return cur.rowcount > 0


def delete_window_results(window: str) -> int:
    """Delete all play_results for a specific window. Returns rows deleted."""
    with _connect() as conn:
        cur = conn.execute("DELETE FROM play_results WHERE window=?", (window,))
        return cur.rowcount


# ─── game cache ───────────────────────────────────────────────────────────────

def clear_games(date: str, through_date: str):
    with _connect() as conn:
        conn.execute(
            "DELETE FROM game_cache WHERE date=? AND through_date=?",
            (date, through_date),
        )


def save_games(date: str, through_date: str, games: list[dict]):
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO game_cache (date, through_date, payload) VALUES (?, ?, ?)",
            (date, through_date, json.dumps(games)),
        )
    log.info(f"Cached {len(games)} games for date={date} through={through_date}")


def load_games(date: str, through_date: str) -> list[dict] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT payload FROM game_cache WHERE date=? AND through_date=?",
            (date, through_date),
        ).fetchone()
    if row:
        log.info(f"Cache hit: date={date} through={through_date}")
        return json.loads(row["payload"])
    return None


# ─── tracked_plays ────────────────────────────────────────────────────────────

def is_auto_tracked(game_id: int, team_abbrev: str, window: str) -> bool:
    """True if this specific window entry already exists for this game+team."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM tracked_plays WHERE game_id=? AND team_abbrev=? AND window=? LIMIT 1",
            (game_id, team_abbrev, window),
        ).fetchone()
    return row is not None


def save_tracked_play(
    game_date: str, game_id: int, team_abbrev: str, team_name: str,
    opponent_abbrev: str, side: str, book_ml: int, book_name: str,
    edge_pct: str, window: str = 'season', fair_ml: int | None = None,
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO tracked_plays
               (game_date, game_id, team_abbrev, team_name, opponent_abbrev,
                side, book_ml, book_name, edge_pct, window, fair_ml)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (game_date, game_id, team_abbrev, team_name, opponent_abbrev,
             side, book_ml, book_name, edge_pct, window, fair_ml),
        )
        return cur.lastrowid


def load_tracked_plays(settled: bool = False) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tracked_plays WHERE settled=? ORDER BY game_date ASC, id ASC",
            (1 if settled else 0,),
        ).fetchall()
    return [dict(r) for r in rows]


def settle_tracked_play(play_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE tracked_plays SET settled=1 WHERE id=?", (play_id,)
        )
        return cur.rowcount > 0


def settle_play_group(game_id: int, team_abbrev: str) -> list[dict]:
    """Return all unsettled tracked_plays for this game+team, then mark them settled."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT * FROM tracked_plays
               WHERE game_id=? AND team_abbrev=? AND settled=0
               ORDER BY window ASC""",
            (game_id, team_abbrev),
        ).fetchall()
        plays = [dict(r) for r in rows]
        if plays:
            conn.execute(
                "UPDATE tracked_plays SET settled=1 WHERE game_id=? AND team_abbrev=? AND settled=0",
                (game_id, team_abbrev),
            )
    return plays


def delete_tracked_play(play_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM tracked_plays WHERE id=?", (play_id,))
        return cur.rowcount > 0


def delete_play_group(game_id: int, team_abbrev: str) -> bool:
    """Delete all unsettled tracked_plays for a game+team."""
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM tracked_plays WHERE game_id=? AND team_abbrev=? AND settled=0",
            (game_id, team_abbrev),
        )
        return cur.rowcount > 0


def is_opponent_tracked(game_id: int, opponent_abbrev: str) -> bool:
    """True if the opposing team already has any tracked play for this game."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM tracked_plays WHERE game_id=? AND team_abbrev=? LIMIT 1",
            (game_id, opponent_abbrev),
        ).fetchone()
    return row is not None


def mark_game_conflict(game_id: int):
    """Set conflict=1 on all tracked_plays for this game."""
    with _connect() as conn:
        conn.execute(
            "UPDATE tracked_plays SET conflict=1 WHERE game_id=?",
            (game_id,),
        )


def load_conflict_pairs() -> dict:
    """
    For each window pair (season/l30, season/l21, l30/l21), return exactly
    one play_result per side per game: the w1-edge team's result on the w1
    side and the w2-edge team's result on the w2 side. This guarantees mirror
    records (if Season is 3-1, L30 must be 1-3) and play count == game count.
    """
    pairs = [('season', 'l30'), ('season', 'l21'), ('l30', 'l21')]
    out = {}
    with _connect() as conn:
        for w1, w2 in pairs:
            # Use tracked_plays to identify WHICH team carried each window's edge.
            raw = conn.execute("""
                SELECT DISTINCT a.game_id,
                       a.team_abbrev AS w1_team,
                       b.team_abbrev AS w2_team
                FROM tracked_plays a
                JOIN tracked_plays b
                  ON a.game_id = b.game_id
                 AND a.opponent_abbrev = b.team_abbrev
                WHERE a.window = ? AND b.window = ?
            """, (w1, w2)).fetchall()

            # Deduplicate to one pair per game (handles symmetric double-tracking)
            seen: set[int] = set()
            conflict_games = []
            for row in raw:
                if row['game_id'] not in seen:
                    seen.add(row['game_id'])
                    conflict_games.append(row)

            rows_w1, rows_w2 = [], []
            for cg in conflict_games:
                r1 = conn.execute(
                    "SELECT * FROM play_results WHERE game_id=? AND team_abbrev=? AND window=? LIMIT 1",
                    (cg['game_id'], cg['w1_team'], w1),
                ).fetchone()
                r2 = conn.execute(
                    "SELECT * FROM play_results WHERE game_id=? AND team_abbrev=? AND window=? LIMIT 1",
                    (cg['game_id'], cg['w2_team'], w2),
                ).fetchone()
                if r1 and r2:  # only include games where both sides are settled
                    rows_w1.append(dict(r1))
                    rows_w2.append(dict(r2))

            rows_w1.sort(key=lambda r: (r['game_date'], r['id']))
            rows_w2.sort(key=lambda r: (r['game_date'], r['id']))

            out[f'{w1}_vs_{w2}'] = {
                w1: rows_w1,
                w2: rows_w2,
                'game_count': len(conflict_games),
            }
    return out


def find_incomplete_conflict_pairs() -> list[dict]:
    """
    Return all conflict pairs where exactly one side has a play_result.
    Each row contains the settled side's result and the missing side's info
    so the caller can write the inverse.
    """
    pairs = [('season', 'l30'), ('season', 'l21'), ('l30', 'l21')]
    missing = []
    with _connect() as conn:
        for w1, w2 in pairs:
            raw = conn.execute("""
                SELECT DISTINCT a.game_id,
                       a.team_abbrev  AS w1_team,
                       b.team_abbrev  AS w2_team,
                       a.game_date
                FROM tracked_plays a
                JOIN tracked_plays b
                  ON a.game_id = b.game_id
                 AND a.opponent_abbrev = b.team_abbrev
                WHERE a.window = ? AND b.window = ?
            """, (w1, w2)).fetchall()

            seen: set[int] = set()
            for row in raw:
                gid = row['game_id']
                if gid in seen:
                    continue
                seen.add(gid)

                r1 = conn.execute(
                    "SELECT * FROM play_results WHERE game_id=? AND team_abbrev=? AND window=? LIMIT 1",
                    (gid, row['w1_team'], w1),
                ).fetchone()
                r2 = conn.execute(
                    "SELECT * FROM play_results WHERE game_id=? AND team_abbrev=? AND window=? LIMIT 1",
                    (gid, row['w2_team'], w2),
                ).fetchone()

                # Only care about pairs with exactly one side settled
                def _missing_book_ml(game_id, team, window, fallback):
                    tp = conn.execute(
                        "SELECT book_ml FROM tracked_plays WHERE game_id=? AND team_abbrev=? AND window=? LIMIT 1",
                        (game_id, team, window),
                    ).fetchone()
                    return tp['book_ml'] if tp else fallback

                if r1 and not r2:
                    missing.append({
                        'game_id': gid, 'game_date': row['game_date'],
                        'known_team': row['w1_team'], 'known_window': w1, 'known_result': r1['result'],
                        'missing_team': row['w2_team'], 'missing_window': w2,
                        'missing_opponent': row['w1_team'],
                        'missing_book_ml': _missing_book_ml(gid, row['w2_team'], w2, r1['book_ml']),
                    })
                elif r2 and not r1:
                    missing.append({
                        'game_id': gid, 'game_date': row['game_date'],
                        'known_team': row['w2_team'], 'known_window': w2, 'known_result': r2['result'],
                        'missing_team': row['w1_team'], 'missing_window': w1,
                        'missing_opponent': row['w2_team'],
                        'missing_book_ml': _missing_book_ml(gid, row['w1_team'], w1, r2['book_ml']),
                    })
    return missing


def load_discrepancies() -> list[dict]:
    """Return one record per conflicting game (earliest play per game_id)."""
    with _connect() as conn:
        rows = conn.execute("""
            SELECT game_id, game_date,
                   GROUP_CONCAT(DISTINCT team_abbrev)  AS teams,
                   GROUP_CONCAT(DISTINCT window)       AS windows,
                   MIN(settled)                        AS any_unsettled,
                   MAX(settled)                        AS any_settled
            FROM tracked_plays
            WHERE conflict = 1
            GROUP BY game_id
            ORDER BY game_date DESC, game_id
        """).fetchall()
    return [dict(r) for r in rows]


# ─── league averages ──────────────────────────────────────────────────────────

def save_league_avgs(through_date: str, avgs: dict):
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO league_avg_cache (through_date, payload) VALUES (?, ?)",
            (through_date, json.dumps(avgs)),
        )


def load_league_avgs(through_date: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT payload FROM league_avg_cache WHERE through_date=?",
            (through_date,),
        ).fetchone()
    return json.loads(row["payload"]) if row else None
