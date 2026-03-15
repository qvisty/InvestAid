"""
InvestAid Dashboard - Signaler & Filtre
Vis de seneste handelssignaler, aktive filtre og strategi-statistik.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@st.cache_data(ttl=30)
def _load_recent_signals(days: int) -> list[dict]:
    try:
        from src.database import get_recent_signals
        return get_recent_signals(limit=200, days=days)
    except Exception:
        return []


@st.cache_data(ttl=30)
def _load_signal_stats(days: int) -> list[dict]:
    try:
        from src.database import get_signal_stats
        return get_signal_stats(days=days)
    except Exception:
        return []


@st.cache_data(ttl=60)
def _load_filter_status() -> dict:
    """
    Hent live markeds-regime og filter-status for alle symboler i watchlisten.
    Kræver internetforbindelse — data hentes via yfinance (samme kilde som botten).
    """
    try:
        from src.config import get_config
        from src.data.market_data import get_multiple_symbols
        from src.strategies.filters import adx_filter, regime_filter, volume_filter

        cfg = get_config()
        symbols = cfg.watchlist.symbols[:15]  # Begræns til 15 for hastighed
        data = get_multiple_symbols(symbols, period="1y", interval="1d")

        result = {}
        for symbol, df in data.items():
            if df is None or df.empty:
                continue
            close = df["Close"]
            volume = df["Volume"] if "Volume" in df.columns else None
            result[symbol] = {
                "regime": regime_filter(close),
                "adx": adx_filter(df),
                "volume": volume_filter(volume) if volume is not None else None,
                "price": float(close.iloc[-1]),
                "ma200": float(close.rolling(min(200, len(close))).mean().iloc[-1]),
            }
        return result
    except Exception:
        return {}


def show_signals():
    st.title("Signaler & Filtre")
    st.caption(
        "Her kan du se hvilke signaler systemet genererer, og hvilke filtre der er aktive. "
        "Filtrene beskytter mod falske signaler i bear-markeder og sideværts markeder."
    )

    days = st.slider("Vis signaler fra de seneste", 7, 90, 30, step=7, format="%d dage")

    # ------------------------------------------------------------------ #
    #  Sektion 1: Markedsregime-oversigt                                  #
    # ------------------------------------------------------------------ #
    st.subheader("Markedsregime")
    st.caption(
        "Regime-filteret sammenligner aktuel kurs med 200-dages glidende gennemsnit. "
        "Bull-regime = KØB tilladt. Bear-regime = KØB blokeret (kun SÆLG/HOLD)."
    )

    with st.spinner("Henter live markedsdata..."):
        filter_status = _load_filter_status()

    if filter_status:
        bull_symbols = [s for s, v in filter_status.items() if v["regime"]]
        bear_symbols = [s for s, v in filter_status.items() if not v["regime"]]

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Bull-regime (KØB tilladt)", len(bull_symbols))
        with col2:
            st.metric("Bear-regime (KØB blokeret)", len(bear_symbols))

        rows = []
        for symbol, info in sorted(filter_status.items()):
            regime_icon = "🟢 Bull" if info["regime"] else "🔴 Bear"
            adx_icon = "✅ Trend" if info["adx"] else "⚠️ Sideværts"
            vol_icon = (
                "✅ Ok" if info["volume"] is True
                else ("⚠️ Lav" if info["volume"] is False else "—")
            )
            pct_from_ma = (info["price"] - info["ma200"]) / info["ma200"] * 100
            rows.append({
                "Symbol": symbol,
                "Kurs": f"${info['price']:.2f}",
                "MA200": f"${info['ma200']:.2f}",
                "Afstand MA": f"{pct_from_ma:+.1f}%",
                "Regime": regime_icon,
                "ADX": adx_icon,
                "Volumen": vol_icon,
            })

        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Ingen live data tilgængelig (botten er ikke forbundet eller kørende).")

    st.divider()

    # ------------------------------------------------------------------ #
    #  Sektion 2: Seneste signaler                                        #
    # ------------------------------------------------------------------ #
    st.subheader(f"Seneste signaler ({days} dage)")

    signals = _load_recent_signals(days)

    if not signals:
        st.info(
            "Ingen signaler i databasen endnu. "
            "Start botten og vent på næste trading-cyklus."
        )
    else:
        df = pd.DataFrame(signals)
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%d/%m %H:%M")
        df["strength"] = df["strength"].map(lambda x: f"{x:.0%}")
        df["signal"] = df["signal"].map(
            lambda x: "🟢 KØB" if x == "buy" else ("🔴 SÆLG" if x == "sell" else x)
        )
        df = df.rename(columns={
            "timestamp": "Tid",
            "symbol": "Symbol",
            "strategy": "Strategi",
            "signal": "Signal",
            "strength": "Styrke",
            "price": "Kurs",
            "notes": "Noter",
        })
        df["Kurs"] = df["Kurs"].map(lambda x: f"${x:.2f}" if pd.notna(x) else "—")
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    # ------------------------------------------------------------------ #
    #  Sektion 3: Strategi-statistik                                      #
    # ------------------------------------------------------------------ #
    st.subheader(f"Strategi-statistik ({days} dage)")
    st.caption("Antal signaler genereret per strategi — både filtrerede og ikke-filtrerede.")

    stats = _load_signal_stats(days)

    if not stats:
        st.info("Ingen statistik endnu — start botten for at samle data.")
    else:
        stats_df = pd.DataFrame(stats)
        pivot = stats_df.pivot_table(
            index="strategy", columns="signal", values="count", fill_value=0
        ).reset_index()
        pivot.columns.name = None

        # Ensret kolonnenavne uanset hvilke signaltyper der findes
        for col in ["buy", "sell", "hold"]:
            if col not in pivot.columns:
                pivot[col] = 0

        pivot = pivot.rename(columns={
            "strategy": "Strategi",
            "buy": "KØB",
            "sell": "SÆLG",
            "hold": "HOLD",
        })
        pivot["Total"] = pivot.get("KØB", 0) + pivot.get("SÆLG", 0) + pivot.get("HOLD", 0)
        st.dataframe(pivot, use_container_width=True, hide_index=True)

    st.divider()

    # ------------------------------------------------------------------ #
    #  Sektion 4: Forklaring af filtrene                                  #
    # ------------------------------------------------------------------ #
    with st.expander("Hvad gør filtrene? (klik for at udvide)"):
        st.markdown("""
**Regime-filter (200-dages MA)**
Sammenligner aktuel kurs med 200-dages glidende gennemsnit. Hvis kursen er under MA,
er vi i et bear-marked — systemet blokerer alle nye KØB-signaler. SÆLG-signaler
passerer altid (du skal stadig kunne komme ud af tabspositioner).
_Kilde: Meb Faber (2007), Gary Antonacci (2014) — reducerer max drawdown med 30-40%._

---

**ADX-filter (trendstyrke)**
ADX måler om markedet er trendende (ADX > 22) eller sideværts (ADX < 22).
EMA Crossover-strategien er kun pålidelig i trendende markeder — i sideværts markeder
genererer den mange falske "whipsaw"-signaler. ADX-filteret blokerer disse.
_Kilde: J. Welles Wilder, "New Concepts in Technical Trading Systems" (1978)._

---

**Volumen-filter**
Bekræfter RSI-signaler med volumen over 20-dages gennemsnit. Et oversold-recovery
signal med høj volumen er markant mere pålideligt end ét med lav volumen — høj volumen
indikerer at mange markedsdeltagere handler i den samme retning.
_Kilde: William O'Neil, "How to Make Money in Stocks" (1988)._

---

**ATR-baseret positionsstørrelse**
I stedet for en fast positionsstørrelse bruges ATR (Average True Range) til at
justere størrelsen: høj-volatilitet aktiver (f.eks. krypto) får en mindre position,
lav-volatilitet aktiver (f.eks. obligationer ETF'er) får en større position.
Dette sikrer at alle positioner har omtrent samme risiko i dollar-termer.
_Kilde: Van Tharp, "Trade Your Way to Financial Freedom" (1999)._
        """)
