"""
InvestAid - Scheduler
Automatisk kørsel af trading-cyklusser i markedstimer via APScheduler.
"""

import logging
import signal
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .config import get_config
from .data.market_data import is_market_open
from .portfolio_manager import PortfolioManager

logger = logging.getLogger(__name__)

_manager: PortfolioManager | None = None
_scheduler: BlockingScheduler | None = None


def _run_trading_cycle() -> None:
    """Kald PortfolioManager.run_cycle() hvis markedet er åbent"""
    global _manager

    cfg = get_config()
    tz = ZoneInfo(cfg.scheduler.timezone)
    now = datetime.now(tz)

    if not cfg.scheduler.run_on_weekends and now.weekday() >= 5:
        logger.debug("Weekend - springer trading-cyklus over")
        return

    if not is_market_open():
        logger.debug(f"Markedet er lukket ({now.strftime('%H:%M %Z')}) - springer over")
        return

    if _manager is None:
        _manager = PortfolioManager()

    logger.info(f"Starter trading-cyklus kl. {now.strftime('%H:%M:%S %Z')}")
    try:
        summary = _manager.run_cycle()
        logger.info(f"Cyklus færdig: {summary}")
    except Exception as e:
        logger.error(f"Fejl i trading-cyklus: {e}", exc_info=True)


def _handle_shutdown(signum, frame):
    """Graceful shutdown ved Ctrl+C eller SIGTERM"""
    logger.info("Modtog stop-signal - lukker scheduler ned...")
    if _scheduler:
        _scheduler.shutdown(wait=False)
    sys.exit(0)


def start_scheduler() -> None:
    """
    Start den automatiske trading-scheduler.
    Blokerer indtil programmet stoppes med Ctrl+C.
    """
    global _scheduler, _manager

    cfg = get_config()
    mode = "PAPER" if cfg.is_paper_mode else "LIVE"

    logger.info(f"=== InvestAid Scheduler starter ({mode}) ===")
    logger.info(f"Interval: hvert {cfg.strategy.check_interval_minutes} minut(ter)")
    logger.info(f"Tidszone: {cfg.scheduler.timezone}")
    logger.info(f"Markedstimer: {cfg.scheduler.market_open} - {cfg.scheduler.market_close}")

    # Initialiser manager
    _manager = PortfolioManager()

    _scheduler = BlockingScheduler(timezone=cfg.scheduler.timezone)

    # Tilføj trading-job
    _scheduler.add_job(
        func=_run_trading_cycle,
        trigger=IntervalTrigger(minutes=cfg.strategy.check_interval_minutes),
        id="trading_cycle",
        name="Trading Cyklus",
        replace_existing=True,
    )

    # Daglig portfolio snapshot (kl. 16:01 ET - lige efter markedslukning)
    _scheduler.add_job(
        func=_save_daily_snapshot,
        trigger=CronTrigger(
            hour=16, minute=1,
            timezone=cfg.scheduler.timezone,
            day_of_week="mon-fri",
        ),
        id="daily_snapshot",
        name="Daglig Portfolio Snapshot",
        replace_existing=True,
    )

    # Registrer shutdown handlers
    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    logger.info("Scheduler kører. Tryk Ctrl+C for at stoppe.")
    logger.info(f"Næste kørsel om {cfg.strategy.check_interval_minutes} minutter (hvis markedet er åbent)")

    try:
        _scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stoppet.")


def _save_daily_snapshot() -> None:
    """Gem daglig portefølje snapshot"""
    global _manager
    if _manager is None:
        _manager = PortfolioManager()

    try:
        status = _manager.get_portfolio_status()
        if status.get("connected") and status.get("account"):
            account = status["account"]
            from .database import save_portfolio_snapshot
            save_portfolio_snapshot(
                total_value=account["portfolio_value"],
                cash=account["cash"],
                invested=account["portfolio_value"] - account["cash"],
                paper=status.get("paper_mode", True),
            )
            logger.info(f"Daglig snapshot gemt: ${account['portfolio_value']:,.2f}")
    except Exception as e:
        logger.error(f"Fejl ved gemning af daglig snapshot: {e}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    start_scheduler()
