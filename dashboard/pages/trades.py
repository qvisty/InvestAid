"""
InvestAid Dashboard - Handelshistorik
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.database import Trade, get_session


def show_trades(paper_mode: bool = True) -> None:
    st.header("Handelshistorik")

    trades_df = _load_trades(paper_mode)

    if trades_df.empty:
        st.info("Ingen handler endnu. Botten logger alle handler her automatisk.")
        return

    # Statistik
    buys = trades_df[trades_df["side"] == "buy"]
    sells = trades_df[trades_df["side"] == "sell"]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Totale handler", len(trades_df))
    with col2:
        st.metric("Køb", len(buys))
    with col3:
        st.metric("Salg", len(sells))

    st.divider()

    # Filter
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        side_filter = st.selectbox("Retning", ["Alle", "Køb", "Sælg"])
    with col_f2:
        symbols = ["Alle"] + sorted(trades_df["symbol"].unique().tolist())
        symbol_filter = st.selectbox("Symbol", symbols)

    filtered = trades_df.copy()
    if side_filter == "Køb":
        filtered = filtered[filtered["side"] == "buy"]
    elif side_filter == "Sælg":
        filtered = filtered[filtered["side"] == "sell"]
    if symbol_filter != "Alle":
        filtered = filtered[filtered["symbol"] == symbol_filter]

    # Tabel
    display = filtered.rename(columns={
        "timestamp": "Tidspunkt",
        "symbol": "Symbol",
        "side": "Retning",
        "qty": "Antal",
        "price": "Pris",
        "strategy": "Strategi",
        "status": "Status",
    })
    display["Retning"] = display["Retning"].map({"buy": "KØB", "sell": "SÆLG"})
    display["Pris"] = display["Pris"].apply(lambda x: f"${x:,.2f}" if x else "–")
    display["Antal"] = display["Antal"].apply(lambda x: f"{x:.4f}" if x else "–")
    display["Tidspunkt"] = pd.to_datetime(display["Tidspunkt"]).dt.strftime("%d/%m/%Y %H:%M")

    st.dataframe(
        display[["Tidspunkt", "Symbol", "Retning", "Antal", "Pris", "Strategi", "Status"]],
        use_container_width=True,
        hide_index=True,
    )


def _load_trades(paper: bool) -> pd.DataFrame:
    try:
        with get_session() as session:
            rows = (
                session.query(Trade)
                .filter(Trade.paper == paper)
                .order_by(Trade.timestamp.desc())
                .limit(200)
                .all()
            )
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame([
                {
                    "timestamp": r.timestamp,
                    "symbol": r.symbol,
                    "side": r.side,
                    "qty": r.qty,
                    "price": r.price,
                    "strategy": r.strategy or "–",
                    "status": r.status,
                }
                for r in rows
            ])
    except Exception:
        return pd.DataFrame()
