"""
InvestAid Dashboard - Åbne Positioner
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def show_positions(portfolio_status: dict) -> None:
    st.header("Åbne Positioner")

    if not portfolio_status.get("connected"):
        st.warning("Ikke forbundet til Alpaca.")
        return

    positions = portfolio_status.get("positions", [])

    if not positions:
        st.info("Ingen åbne positioner. Botten handler automatisk når der opstår signaler.")
        return

    # Samlet P&L
    total_pl = sum(p["unrealized_pl"] for p in positions)
    total_value = sum(p["market_value"] for p in positions)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Antal positioner", len(positions))
    with col2:
        st.metric("Samlet investeret", f"${total_value:,.2f}")
    with col3:
        color = "normal" if total_pl >= 0 else "inverse"
        st.metric(
            "Urealiseret P&L",
            f"${total_pl:,.2f}",
            f"{total_pl/total_value*100:.2f}%" if total_value else "",
            delta_color=color,
        )

    st.divider()

    # Positionstabel
    df = pd.DataFrame(positions)
    df = df.rename(columns={
        "symbol": "Symbol",
        "qty": "Antal",
        "avg_entry_price": "Købspris",
        "current_price": "Nuv. pris",
        "market_value": "Markedsværdi",
        "unrealized_pl": "P&L (USD)",
        "unrealized_plpc": "P&L (%)",
    })

    df["P&L (%)"] = df["P&L (%)"].map(lambda x: f"{float(x)*100:.2f}%")
    df["Købspris"] = df["Købspris"].map(lambda x: f"${x:,.2f}")
    df["Nuv. pris"] = df["Nuv. pris"].map(lambda x: f"${x:,.2f}")
    df["Markedsværdi"] = df["Markedsværdi"].map(lambda x: f"${x:,.2f}")
    df["P&L (USD)"] = df["P&L (USD)"].map(lambda x: f"${x:+,.2f}")
    df["Antal"] = df["Antal"].map(lambda x: f"{float(x):.4f}")

    st.dataframe(
        df[["Symbol", "Antal", "Købspris", "Nuv. pris", "Markedsværdi", "P&L (USD)", "P&L (%)"]],
        use_container_width=True,
        hide_index=True,
    )

    # P&L bar chart
    if len(positions) > 1:
        st.subheader("P&L per Position")
        pl_data = pd.DataFrame({
            "Symbol": [p["symbol"] for p in positions],
            "P&L (USD)": [p["unrealized_pl"] for p in positions],
        })
        colors = ["#00C851" if v >= 0 else "#FF4444" for v in pl_data["P&L (USD)"]]
        fig = px.bar(
            pl_data,
            x="Symbol",
            y="P&L (USD)",
            color="P&L (USD)",
            color_continuous_scale=["#FF4444", "#FFD700", "#00C851"],
            title="",
        )
        fig.update_layout(showlegend=False, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)
