"""
InvestAid Dashboard - Oversigt
Viser porteføljeværdi, P&L graf og allokering.
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.database import PortfolioSnapshot, get_session


def show_overview(portfolio_status: dict) -> None:
    st.header("Portefølje Oversigt")

    if not portfolio_status.get("connected"):
        if portfolio_status.get("bot_never_run"):
            st.info(
                "Botten er ikke startet endnu. Kør `python run_bot.py` i en terminal "
                "for at starte automatisk handel. Dashboardet opdateres automatisk.",
                icon="ℹ️",
            )
            _show_setup_guide()
        else:
            st.warning("Ingen data fra botten endnu.", icon="⚠️")
        return

    account = portfolio_status.get("account", {})
    paper_mode = portfolio_status.get("paper_mode", True)

    if paper_mode:
        st.info("Paper Trading tilstand — Simulerede handler med ægte markedsdata", icon="📋")
    else:
        st.error("LIVE Trading tilstand — Rigtige penge!", icon="🔴")

    # Nøgletal
    col1, col2, col3, col4 = st.columns(4)
    portfolio_value = account.get("portfolio_value", 0)
    cash = account.get("cash", 0)
    invested = portfolio_value - cash
    buying_power = account.get("buying_power", 0)

    with col1:
        st.metric("Porteføljeværdi", f"${portfolio_value:,.2f}")
    with col2:
        st.metric("Investeret", f"${invested:,.2f}")
    with col3:
        st.metric("Likvide midler", f"${cash:,.2f}")
    with col4:
        st.metric("Købekraft", f"${buying_power:,.2f}")

    st.divider()

    # P&L historik graf
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.subheader("Porteføljeværdi over tid")
        snapshots = _load_snapshots(paper_mode)
        if not snapshots.empty:
            fig = px.line(
                snapshots,
                x="timestamp",
                y="total_value",
                title="",
                labels={"total_value": "Værdi (USD)", "timestamp": "Dato"},
                color_discrete_sequence=["#00C851"],
            )
            fig.update_layout(
                showlegend=False,
                margin=dict(l=0, r=0, t=10, b=0),
                hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Endnu ingen historik. Kør botten i et stykke tid for at se data.")

    with col_right:
        st.subheader("Allokering")
        positions = portfolio_status.get("positions", [])
        if positions and cash is not None:
            labels = [p["symbol"] for p in positions] + ["Cash"]
            values = [p["market_value"] for p in positions] + [cash]
            fig = px.pie(
                values=values,
                names=labels,
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Set3,
            )
            fig.update_layout(
                showlegend=True,
                margin=dict(l=0, r=0, t=10, b=0),
                legend=dict(orientation="v", x=1, y=0.5),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Ingen åbne positioner endnu.")

    # Risikostatus
    risk = portfolio_status.get("risk", {})
    if risk:
        st.divider()
        st.subheader("Risikostatus")
        rcol1, rcol2, rcol3 = st.columns(3)
        with rcol1:
            halted = risk.get("trading_halted", False)
            if halted:
                st.error("Handel STOPPET (daglig tabsgrænse nået)")
            else:
                st.success("Handel aktiv")
        with rcol2:
            st.metric(
                "Max kapital",
                f"${risk.get('max_portfolio_value', 0):,.0f}",
            )
        with rcol3:
            st.metric(
                "Stop-loss",
                f"{risk.get('stop_loss_pct', 0):.0%} per position",
            )


def _load_snapshots(paper: bool) -> pd.DataFrame:
    try:
        with get_session() as session:
            rows = (
                session.query(PortfolioSnapshot)
                .filter(PortfolioSnapshot.paper == paper)
                .order_by(PortfolioSnapshot.timestamp)
                .limit(500)
                .all()
            )
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame([
                {
                    "timestamp": r.timestamp,
                    "total_value": r.total_value,
                    "cash": r.cash,
                    "invested": r.invested,
                    "daily_pnl": r.daily_pnl,
                }
                for r in rows
            ])
    except Exception:
        return pd.DataFrame()


def _show_setup_guide():
    with st.expander("Sådan opsætter du Alpaca Paper Trading", expanded=True):
        st.markdown("""
        **Trin 1:** Opret gratis konto på [alpaca.markets](https://alpaca.markets)

        **Trin 2:** Gå til **Paper Trading** → **API Keys** → Generer nye nøgler

        **Trin 3:** Kopier `.env.example` til `.env` og indsæt dine nøgler:
        ```
        ALPACA_API_KEY=PKxxxxxxxxxxxxxxxxxxxxxxxx
        ALPACA_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
        LIVE_TRADING=false
        ```

        **Trin 4:** Genstart dashboardet: `streamlit run run_dashboard.py`

        Du starter automatisk med **$100.000 simuleret kapital** (ingen rigtige penge).
        """)
