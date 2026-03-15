"""
InvestAid - Scheduler
Automatisk kørsel af trading-cyklusser i markedstimer via APScheduler.
Inkluderer daglig statusmail og IMAP kill-switch monitor.
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
from .notifications.email_notifier import create_notifier_from_config
from .notifications.kill_switch import create_monitor_from_config, is_kill_switch_active
from .portfolio_manager import PortfolioManager

logger = logging.getLogger(__name__)

_manager: PortfolioManager | None = None
_scheduler: BlockingScheduler | None = None
_kill_switch_monitor = None


def _run_trading_cycle() -> None:
    """Kald PortfolioManager.run_cycle() hvis markedet er åbent og kill-switch ikke aktiv."""
    global _manager

    cfg = get_config()
    tz = ZoneInfo(cfg.scheduler.timezone)
    now = datetime.now(tz)

    if not cfg.scheduler.run_on_weekends and now.weekday() >= 5:
        logger.debug("Weekend - springer trading-cyklus over")
        return

    if is_kill_switch_active():
        logger.warning("Kill-switch aktiv — springer trading-cyklus over")
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
        notifier = create_notifier_from_config()
        notifier.send_system_error(str(e), context="Trading-cyklus fejlede")


def _send_daily_status() -> None:
    """Send daglig statusmail kl. 16:01 (efter markedslukning)."""
    global _manager
    if _manager is None:
        _manager = PortfolioManager()

    try:
        status = _manager.get_portfolio_status()
        if not status.get("connected"):
            return

        account = status.get("account", {})
        positions = status.get("positions", [])

        # Hent dagens handler fra database
        from .database import Trade, get_session
        from datetime import date
        with get_session() as session:
            today = date.today()
            trades_today = (
                session.query(Trade)
                .filter(Trade.timestamp >= datetime(today.year, today.month, today.day))
                .count()
            )

        # Beregn daglig P&L fra snapshot-historik
        from .database import PortfolioSnapshot
        with get_session() as session:
            snapshots = (
                session.query(PortfolioSnapshot)
                .filter(PortfolioSnapshot.paper == status.get("paper_mode", True))
                .order_by(PortfolioSnapshot.timestamp.desc())
                .limit(2)
                .all()
            )

        pv = account.get("portfolio_value", 0)
        if len(snapshots) >= 2:
            prev_value = snapshots[1].total_value
            daily_pnl = pv - prev_value
            daily_pnl_pct = (daily_pnl / prev_value * 100) if prev_value else 0
        else:
            daily_pnl = 0.0
            daily_pnl_pct = 0.0

        notifier = _manager.notifier
        notifier.send_daily_status(
            portfolio_value=pv,
            cash=account.get("cash", 0),
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            positions=positions,
            trades_today=trades_today,
        )

        # Gem snapshot
        from .database import save_portfolio_snapshot
        save_portfolio_snapshot(
            total_value=pv,
            cash=account.get("cash", 0),
            invested=pv - account.get("cash", 0),
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            paper=status.get("paper_mode", True),
        )

    except Exception as e:
        logger.error(f"Fejl ved daglig statusmail: {e}", exc_info=True)


def _handle_shutdown(signum, frame):
    """Graceful shutdown ved Ctrl+C eller SIGTERM."""
    logger.info("Modtog stop-signal - lukker scheduler ned...")
    if _kill_switch_monitor:
        _kill_switch_monitor.stop()
    if _scheduler:
        _scheduler.shutdown(wait=False)
    sys.exit(0)


def start_scheduler() -> None:
    """
    Start den automatiske trading-scheduler.
    Blokerer indtil programmet stoppes med Ctrl+C.
    """
    global _scheduler, _manager, _kill_switch_monitor

    cfg = get_config()
    mode = "PAPER" if cfg.is_paper_mode else "LIVE"

    logger.info(f"=== InvestAid Scheduler starter ({mode}) ===")
    logger.info(f"Interval: hvert {cfg.strategy.check_interval_minutes} minut(ter)")
    logger.info(f"Tidszone: {cfg.scheduler.timezone}")
    logger.info(f"Markedstimer: {cfg.scheduler.market_open} - {cfg.scheduler.market_close}")

    # Initialiser manager og notifier
    _manager = PortfolioManager()

    # Start IMAP kill-switch monitor i baggrundstråd
    _kill_switch_monitor = create_monitor_from_config()
    _kill_switch_monitor.set_notifier(_manager.notifier)
    _kill_switch_monitor.start()

    _scheduler = BlockingScheduler(timezone=cfg.scheduler.timezone)

    # Trading-cyklus job
    _scheduler.add_job(
        func=_run_trading_cycle,
        trigger=IntervalTrigger(minutes=cfg.strategy.check_interval_minutes),
        id="trading_cycle",
        name="Trading Cyklus",
        replace_existing=True,
    )

    # Daglig statusmail kl. 16:01 ET (efter markedslukning)
    _scheduler.add_job(
        func=_send_daily_status,
        trigger=CronTrigger(
            hour=16, minute=1,
            timezone=cfg.scheduler.timezone,
            day_of_week="mon-fri",
        ),
        id="daily_status",
        name="Daglig Statusmail",
        replace_existing=True,
    )

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    logger.info("Scheduler kører. Tryk Ctrl+C for at stoppe.")

    try:
        _scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stoppet.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    start_scheduler()
