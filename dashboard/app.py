"""
InvestAid Dashboard - Streamlit Hoved-App
Start: streamlit run run_dashboard.py

Dashboardet læser KUN fra den lokale SQLite-database.
Det kalder aldrig Alpaca direkte — botten håndterer al broker-kommunikation.
Dette betyder at du kan navigere frit i dashboardet uden at forstyrre botten.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

st.set_page_config(
    page_title="InvestAid",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(ttl=15)
def get_portfolio_status() -> dict:
    """
    Hent seneste porteføljestatus fra databasen.
    TTL=15 sekunder — dashboardet er aldrig mere end 15 sekunder bagud efter botten.
    Ingen Alpaca API-kald herfra.
    """
    try:
        from src.database import get_latest_account, get_latest_positions, get_system_flag

        paper_mode = get_system_flag("paper_mode") != "false"

        account = get_latest_account(paper=paper_mode)
        positions = get_latest_positions(paper=paper_mode)

        if account is None:
            return {"connected": False, "paper_mode": paper_mode, "bot_never_run": True}

        return {
            "connected": True,
            "paper_mode": paper_mode,
            "account": account,
            "positions": positions,
            "risk": _get_risk_status(),
        }
    except Exception:
        return {"connected": False}


def _get_risk_status() -> dict:
    """Hent risikostatus fra settings (ingen broker-kald)."""
    try:
        from src.config import get_config
        cfg = get_config()
        return {
            "trading_halted": False,
            "max_portfolio_value": cfg.risk.max_portfolio_value,
            "max_position_pct": cfg.risk.max_position_pct,
            "stop_loss_pct": cfg.risk.stop_loss_pct,
            "take_profit_pct": cfg.risk.take_profit_pct,
            "max_daily_loss_pct": cfg.risk.max_daily_loss_pct,
            "min_order_notional": cfg.risk.min_order_notional,
        }
    except Exception:
        return {}


def _get_bot_status() -> tuple[str, str]:
    """
    Returner (label, farve) for bot-status baseret på seneste DB-snapshot.
    Grøn: snapshot nyere end 20 min. Gul: 20-60 min. Rød: over 60 min eller aldrig kørt.
    """
    try:
        from src.database import get_bot_last_seen, get_system_flag
        paper_mode = get_system_flag("paper_mode") != "false"
        last_seen = get_bot_last_seen(paper=paper_mode)

        if last_seen is None:
            return "Bot aldrig kørt", "🔴"

        age = datetime.utcnow() - last_seen
        if age < timedelta(minutes=20):
            return f"Bot aktiv ({int(age.total_seconds() / 60)}m siden)", "🟢"
        elif age < timedelta(hours=1):
            return f"Bot inaktiv ({int(age.total_seconds() / 60)}m siden)", "🟡"
        else:
            return f"Bot stoppet ({age.seconds // 3600}t siden)", "🔴"
    except Exception:
        return "Status ukendt", "⚪"


def _has_risk_profile() -> bool:
    """Tjek om brugeren har gennemført setup-wizarden."""
    try:
        from src.database import get_system_flag, init_db
        init_db()
        return get_system_flag("risk_profile") is not None
    except Exception:
        return False


def main():
    # Vis setup-wizard ved første opstart
    if not _has_risk_profile():
        from dashboard.pages.setup import show_setup_wizard
        show_setup_wizard()
        return

    # Sidebar navigation
    with st.sidebar:
        st.title("InvestAid")
        st.caption("Automatisk Investeringsrådgiver")

        # Bot-status
        bot_label, bot_icon = _get_bot_status()
        st.caption(f"{bot_icon} {bot_label}")
        st.divider()

        page = st.radio(
            "Navigation",
            ["Oversigt", "Positioner", "Handelshistorik", "Backtesting", "Simulering", "Indstillinger"],
            label_visibility="collapsed",
        )

        st.divider()

        # Porteføljeværdi hurtig-visning
        status = get_portfolio_status()
        if status.get("connected"):
            paper = status.get("paper_mode", True)
            mode_label = "PAPER" if paper else "LIVE"
            mode_color = "🟡" if paper else "🔴"
            st.caption(f"{mode_color} {mode_label} tilstand")

            account = status.get("account", {})
            if account:
                st.metric("Portefølje", f"${account.get('portfolio_value', 0):,.0f}")
        else:
            if status.get("bot_never_run"):
                st.caption("⚪ Botten er ikke startet endnu")
            else:
                st.caption("🔴 Ingen data fra botten")

        st.divider()
        if st.button("Opdater"):
            st.cache_data.clear()
            st.rerun()

    # Vis valgt side
    portfolio_status = get_portfolio_status()

    if page == "Oversigt":
        from dashboard.pages.overview import show_overview
        show_overview(portfolio_status)

    elif page == "Positioner":
        from dashboard.pages.positions import show_positions
        show_positions(portfolio_status)

    elif page == "Handelshistorik":
        from dashboard.pages.trades import show_trades
        paper_mode = portfolio_status.get("paper_mode", True)
        show_trades(paper_mode)

    elif page == "Backtesting":
        from dashboard.pages.backtest import show_backtest
        show_backtest()

    elif page == "Simulering":
        from dashboard.pages.simulation import show_simulation
        show_simulation()

    elif page == "Indstillinger":
        from dashboard.pages.settings import show_settings
        show_settings()


if __name__ == "__main__":
    main()
