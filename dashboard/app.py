"""
InvestAid Dashboard - Streamlit Hoved-App
Start: streamlit run run_dashboard.py
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

st.set_page_config(
    page_title="InvestAid",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource(ttl=30)
def get_portfolio_manager():
    """Initialiser PortfolioManager (cached, opdateres hvert 30. sekund)"""
    try:
        from src.portfolio_manager import PortfolioManager
        return PortfolioManager()
    except Exception as e:
        return None


@st.cache_data(ttl=30)
def get_portfolio_status():
    """Hent porteføljestatus (cached, opdateres hvert 30. sekund)"""
    manager = get_portfolio_manager()
    if manager is None:
        return {"connected": False}
    try:
        return manager.get_portfolio_status()
    except Exception:
        return {"connected": False}


def main():
    # Sidebar navigation
    with st.sidebar:
        st.title("InvestAid")
        st.caption("Automatisk Investeringsrådgiver")
        st.divider()

        page = st.radio(
            "Navigation",
            ["Oversigt", "Positioner", "Handelshistorik", "Backtesting", "Indstillinger"],
            label_visibility="collapsed",
        )

        st.divider()

        # Status indikator
        status = get_portfolio_status()
        if status.get("connected"):
            paper = status.get("paper_mode", True)
            mode_label = "PAPER" if paper else "LIVE"
            mode_color = "🟡" if paper else "🔴"
            st.caption(f"{mode_color} {mode_label} tilstand")

            account = status.get("account", {})
            if account:
                st.metric(
                    "Portefølje",
                    f"${account.get('portfolio_value', 0):,.0f}",
                    label_visibility="visible",
                )
        else:
            st.caption("🔴 Ikke forbundet")

        st.divider()
        if st.button("Opdater data"):
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

    elif page == "Indstillinger":
        from dashboard.pages.settings import show_settings
        show_settings()


if __name__ == "__main__":
    main()
