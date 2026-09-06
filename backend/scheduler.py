"""
Step 9: Daily auto-refresh scheduler

Jobs:
  - 6:00 AM CT: bust cache and pre-warm for today's games
  - Top of every hour: re-fetch odds for today (lines move)
"""

import logging
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger(__name__)


def setup_scheduler(analyze_fn) -> AsyncIOScheduler:
    """
    Register scheduled jobs and start the scheduler.
    analyze_fn: callable(game_date: str, through_date: str) → list[dict]
    """
    scheduler = AsyncIOScheduler(timezone="America/Chicago")

    def _today_str():
        return date.today().strftime("%Y-%m-%d")

    def _yesterday_str():
        return (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    async def daily_stats_refresh():
        today, yesterday = _today_str(), _yesterday_str()
        log.info(f"[Scheduler] Daily refresh: games={today}, through={yesterday}")
        try:
            from backend import db
            db.clear_games(today, yesterday)
            games = analyze_fn(today, yesterday)
            log.info(f"[Scheduler] Cached {len(games)} games for {today}")
        except Exception as e:
            log.error(f"[Scheduler] Daily refresh failed: {e}")

    async def odds_refresh():
        today, yesterday = _today_str(), _yesterday_str()
        log.info(f"[Scheduler] Hourly odds refresh for {today}")
        try:
            from backend import db
            if db.load_games(today, yesterday) is not None:
                db.clear_games(today, yesterday)
                analyze_fn(today, yesterday)
                log.info("[Scheduler] Odds refresh complete")
        except Exception as e:
            log.error(f"[Scheduler] Odds refresh failed: {e}")

    scheduler.add_job(
        daily_stats_refresh,
        CronTrigger(hour=6, minute=0),
        id="daily_stats_refresh",
        replace_existing=True,
    )
    scheduler.add_job(
        odds_refresh,
        CronTrigger(minute=0),
        id="odds_refresh",
        replace_existing=True,
    )

    scheduler.start()
    log.info("Scheduler started — daily 6 AM CT, odds hourly")
    return scheduler
