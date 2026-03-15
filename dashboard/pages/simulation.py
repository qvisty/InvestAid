"""
InvestAid Dashboard - Simulering & Stress-test
5-års historisk replay + Monte Carlo + kendte markedskriser.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.market_data import get_close_prices, get_historical_data

# Kendte markedskriser (start-dato, slut-dato, label)
CRISIS_PERIODS = {
    "COVID-krakket (feb–mar 2020)": ("2020-01-15", "2020-04-01"),
    "Finanskrisen 2008–2009": ("2007-10-01", "2009-04-01"),
    "Dot-com krisen 2000–2002": ("2000-03-01", "2002-10-01"),
    "Flash Crash (maj 2010)": ("2010-04-15", "2010-07-01"),
    "Rentechok 2022": ("2021-12-01", "2022-10-01"),
}


def show_simulation() -> None:
    st.header("Simulering & Stress-test")

    tab1, tab2, tab3 = st.tabs([
        "5-års historisk replay",
        "Monte Carlo (fremtid)",
        "Kendte markedskriser",
    ])

    with tab1:
        _show_historical_replay()

    with tab2:
        _show_monte_carlo()

    with tab3:
        _show_stress_test()


# ------------------------------------------------------------------ #
#  Tab 1: Historisk replay                                            #
# ------------------------------------------------------------------ #

def _show_historical_replay() -> None:
    st.subheader("5-års historisk replay")
    st.caption(
        "Kør botens strategi på 5 års historiske data og se hvad der ville være sket. "
        "Ingen rigtige penge involveret."
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        symbol = st.text_input("Symbol", value="SPY", key="replay_sym")
    with col2:
        initial_cash = st.number_input(
            "Start kapital (USD)", min_value=500, max_value=500_000,
            value=5000, step=500, key="replay_cash",
        )
    with col3:
        strategy = st.selectbox(
            "Strategi", ["EMA Crossover", "RSI Momentum", "Kombineret"],
            key="replay_strat",
        )

    col4, col5 = st.columns(2)
    with col4:
        fast_ema = st.slider("Hurtig EMA", 5, 50, 12, key="replay_fast")
        rsi_oversold = st.slider("RSI Oversold", 15, 45, 30, key="replay_rsi_low")
    with col5:
        slow_ema = st.slider("Langsom EMA", 15, 200, 26, key="replay_slow")
        rsi_overbought = st.slider("RSI Overbought", 55, 85, 70, key="replay_rsi_high")

    stop_loss = st.slider("Stop-loss (%)", 1, 20, 5, key="replay_sl") / 100
    take_profit = st.slider("Take-profit (%)", 5, 100, 15, key="replay_tp") / 100

    if st.button("Kør 5-års replay", type="primary", key="replay_btn"):
        with st.spinner(f"Henter 5 års data og simulerer {symbol}..."):
            _run_replay(
                symbol, initial_cash, strategy,
                fast_ema, slow_ema, rsi_oversold, rsi_overbought,
                stop_loss, take_profit,
            )


def _run_replay(
    symbol: str,
    initial_cash: float,
    strategy: str,
    fast_ema: int,
    slow_ema: int,
    rsi_oversold: int,
    rsi_overbought: int,
    stop_loss: float,
    take_profit: float,
) -> None:
    import pandas_ta as ta

    df = get_historical_data(symbol.upper(), period="5y", interval="1d")
    if df.empty:
        st.error(f"Ingen data for {symbol}")
        return

    close = df["Close"]

    # Beregn indikatorer
    ema_fast = ta.ema(close, length=fast_ema)
    ema_slow = ta.ema(close, length=slow_ema)
    rsi = ta.rsi(close, length=14)

    # Generer signaler
    if strategy == "EMA Crossover":
        entries = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))
        exits = (ema_fast < ema_slow) & (ema_fast.shift(1) >= ema_slow.shift(1))
    elif strategy == "RSI Momentum":
        entries = (rsi < rsi_oversold) & (rsi.shift(1) >= rsi_oversold)
        exits = (rsi > rsi_overbought) & (rsi.shift(1) <= rsi_overbought)
    else:
        entries = (
            ((ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1)))
            | ((rsi < rsi_oversold) & (rsi.shift(1) >= rsi_oversold))
        )
        exits = (
            ((ema_fast < ema_slow) & (ema_fast.shift(1) >= ema_slow.shift(1)))
            | ((rsi > rsi_overbought) & (rsi.shift(1) <= rsi_overbought))
        )

    entries = entries.fillna(False)
    exits = exits.fillna(False)

    # Simuler portefølje med stop-loss og take-profit
    pf_values, trades, entry_price = _simulate_portfolio(
        close, entries, exits, initial_cash, stop_loss, take_profit
    )

    # Buy & Hold
    bh_values = (close / close.iloc[0]) * initial_cash

    # Statistik
    final_value = pf_values[-1]
    total_return = (final_value / initial_cash - 1) * 100
    bh_return = (bh_values.iloc[-1] / initial_cash - 1) * 100

    pf_series = pd.Series(pf_values, index=close.index)
    drawdowns = _compute_drawdown(pf_series)
    max_dd = drawdowns.min() * 100
    sharpe = _compute_sharpe(pf_series)

    # Vis resultater
    st.success(f"Replay færdig: {symbol} over {len(df)/252:.1f} år ({len(trades)} handler)")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        delta_vs_bh = total_return - bh_return
        st.metric(
            "Samlet afkast",
            f"{total_return:.1f}%",
            f"{delta_vs_bh:+.1f}% vs Buy&Hold",
            delta_color="normal" if delta_vs_bh >= 0 else "inverse",
        )
    with col2:
        st.metric("Buy & Hold", f"{bh_return:.1f}%")
    with col3:
        st.metric("Max Drawdown", f"{max_dd:.1f}%")
    with col4:
        st.metric("Sharpe Ratio", f"{sharpe:.2f}", help="Over 1.0 er godt")

    col5, col6, col7 = st.columns(3)
    with col5:
        st.metric("Slut-kapital", f"${final_value:,.0f}")
    with col6:
        st.metric("Antal handler", len(trades))
    with col7:
        win_trades = [t for t in trades if t > 0]
        win_rate = len(win_trades) / len(trades) * 100 if trades else 0
        st.metric("Win rate", f"{win_rate:.0f}%")

    # Graf
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=close.index, y=pf_series,
        name=f"Strategi ({strategy})",
        line=dict(color="#00C851", width=2),
        hovertemplate="$%{y:,.0f}<extra>Strategi</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=close.index, y=bh_values,
        name="Buy & Hold",
        line=dict(color="#888", width=1.5, dash="dash"),
        hovertemplate="$%{y:,.0f}<extra>Buy & Hold</extra>",
    ))
    fig.update_layout(
        title=f"{symbol} — {strategy} vs Buy & Hold (5 år)",
        yaxis_title="Porteføljeværdi (USD)",
        hovermode="x unified",
        legend=dict(x=0, y=1),
        margin=dict(l=0, r=0, t=40, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Drawdown
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=drawdowns.index, y=drawdowns * 100,
        fill="tozeroy",
        name="Drawdown %",
        line=dict(color="#FF4444", width=1),
        hovertemplate="%{y:.1f}%<extra>Drawdown</extra>",
    ))
    fig2.update_layout(
        title="Drawdown over tid",
        yaxis_title="Drawdown (%)",
        margin=dict(l=0, r=0, t=40, b=0),
    )
    st.plotly_chart(fig2, use_container_width=True)


# ------------------------------------------------------------------ #
#  Tab 2: Monte Carlo                                                  #
# ------------------------------------------------------------------ #

def _show_monte_carlo() -> None:
    st.subheader("Monte Carlo — fremtidssimulering")
    st.caption(
        "Simulerer 500 mulige fremtidsscenarier baseret på historisk volatilitet. "
        "Viser ikke forudsigelser — kun sandsynlighedsintervaller."
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        symbol = st.text_input("Symbol", value="SPY", key="mc_sym")
    with col2:
        initial_cash = st.number_input(
            "Start kapital (USD)", min_value=500, max_value=500_000,
            value=5000, step=500, key="mc_cash",
        )
    with col3:
        years = st.slider("Simuleringshorisont (år)", 1, 10, 5, key="mc_years")

    n_sims = st.slider("Antal scenarier", 100, 2000, 500, step=100, key="mc_sims")

    if st.button("Kør Monte Carlo", type="primary", key="mc_btn"):
        with st.spinner("Simulerer..."):
            _run_monte_carlo(symbol, initial_cash, years, n_sims)


def _run_monte_carlo(
    symbol: str,
    initial_cash: float,
    years: int,
    n_sims: int,
) -> None:
    df = get_historical_data(symbol.upper(), period="5y", interval="1d")
    if df.empty:
        st.error(f"Ingen data for {symbol}")
        return

    close = df["Close"]
    daily_returns = close.pct_change().dropna()
    mu = daily_returns.mean()
    sigma = daily_returns.std()
    n_days = years * 252

    # Simulér
    rng = np.random.default_rng(seed=42)
    simulations = np.zeros((n_sims, n_days))
    simulations[:, 0] = initial_cash

    for day in range(1, n_days):
        rand_returns = rng.normal(mu, sigma, n_sims)
        simulations[:, day] = simulations[:, day - 1] * (1 + rand_returns)

    final_values = simulations[:, -1]
    p5 = np.percentile(final_values, 5)
    p25 = np.percentile(final_values, 25)
    p50 = np.percentile(final_values, 50)
    p75 = np.percentile(final_values, 75)
    p95 = np.percentile(final_values, 95)

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Worst 5%", f"${p5:,.0f}", f"{(p5/initial_cash-1)*100:.0f}%",
                  delta_color="inverse" if p5 < initial_cash else "normal")
    with col2:
        st.metric("25. percentil", f"${p25:,.0f}", f"{(p25/initial_cash-1)*100:.0f}%",
                  delta_color="inverse" if p25 < initial_cash else "normal")
    with col3:
        st.metric("Median", f"${p50:,.0f}", f"{(p50/initial_cash-1)*100:.0f}%",
                  delta_color="inverse" if p50 < initial_cash else "normal")
    with col4:
        st.metric("75. percentil", f"${p75:,.0f}", f"{(p75/initial_cash-1)*100:.0f}%")
    with col5:
        st.metric("Best 5%", f"${p95:,.0f}", f"{(p95/initial_cash-1)*100:.0f}%")

    # Chance for tab
    loss_pct = (final_values < initial_cash).mean() * 100
    st.info(
        f"Sandsynlighed for tab efter {years} år: **{loss_pct:.1f}%** "
        f"(baseret på {symbol} historisk volatilitet)"
    )

    # Graf: subset af simuleringer + percentil-bånd
    date_range = pd.date_range(start=df.index[-1], periods=n_days, freq="B")

    fig = go.Figure()

    # Vis 50 tilfældige simuleringer svagt
    for i in range(min(50, n_sims)):
        fig.add_trace(go.Scatter(
            x=date_range, y=simulations[i],
            mode="lines",
            line=dict(color="rgba(0,180,100,0.08)", width=1),
            showlegend=False,
            hoverinfo="skip",
        ))

    # Percentil-bånd
    p5_path = np.percentile(simulations, 5, axis=0)
    p95_path = np.percentile(simulations, 95, axis=0)
    p50_path = np.percentile(simulations, 50, axis=0)

    fig.add_trace(go.Scatter(
        x=list(date_range) + list(date_range[::-1]),
        y=list(p95_path) + list(p5_path[::-1]),
        fill="toself",
        fillcolor="rgba(0,180,100,0.15)",
        line=dict(color="rgba(0,0,0,0)"),
        name="5–95% interval",
    ))
    fig.add_trace(go.Scatter(
        x=date_range, y=p50_path,
        name="Median",
        line=dict(color="#00C851", width=2),
    ))
    fig.add_hline(
        y=initial_cash, line_dash="dot",
        line_color="gray", annotation_text="Start kapital",
    )
    fig.update_layout(
        title=f"Monte Carlo: {symbol} over {years} år ({n_sims} scenarier)",
        yaxis_title="Porteføljeværdi (USD)",
        margin=dict(l=0, r=0, t=40, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)


# ------------------------------------------------------------------ #
#  Tab 3: Stress-test mod kendte kriser                               #
# ------------------------------------------------------------------ #

def _show_stress_test() -> None:
    st.subheader("Stress-test mod kendte markedskriser")
    st.caption(
        "Se hvad der ville være sket med din portefølje under historiske markedskriser, "
        "og om stop-loss ville have beskyttet dig."
    )

    col1, col2 = st.columns(2)
    with col1:
        crisis = st.selectbox("Vælg krise", list(CRISIS_PERIODS.keys()), key="crisis_sel")
    with col2:
        initial_cash = st.number_input(
            "Start kapital (USD)", min_value=500, max_value=500_000,
            value=5000, step=500, key="crisis_cash",
        )

    symbols_input = st.text_input(
        "Symboler (kommasepareret)",
        value="SPY, QQQ, GLD",
        key="crisis_syms",
    )

    col3, col4 = st.columns(2)
    with col3:
        stop_loss = st.slider("Stop-loss (%)", 1, 30, 5, key="crisis_sl") / 100
    with col4:
        use_stop_loss = st.toggle("Aktiver stop-loss i simulering", value=True, key="crisis_sl_on")

    if st.button("Kør stress-test", type="primary", key="crisis_btn"):
        with st.spinner("Henter krisedata og simulerer..."):
            symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]
            start, end = CRISIS_PERIODS[crisis]
            _run_stress_test(crisis, symbols, initial_cash, start, end, stop_loss, use_stop_loss)


def _run_stress_test(
    crisis_name: str,
    symbols: list[str],
    initial_cash: float,
    start: str,
    end: str,
    stop_loss: float,
    use_stop_loss: bool,
) -> None:
    # Hent data for en bredere periode (6 måneder ekstra på hver side)
    all_data = {}
    for sym in symbols:
        df = get_historical_data(sym, period="10y", interval="1d")
        if not df.empty:
            crisis_df = df.loc[start:end]
            if not crisis_df.empty:
                all_data[sym] = crisis_df

    if not all_data:
        st.error("Ingen data tilgængelig for den valgte periode og symboler")
        return

    st.markdown(f"### {crisis_name}")

    results = []
    fig = go.Figure()
    colors = ["#00C851", "#FF8800", "#2196F3", "#E91E63", "#9C27B0"]

    for i, (sym, df) in enumerate(all_data.items()):
        close = df["Close"]
        # Normalisér til startkapital
        normalized = (close / close.iloc[0]) * initial_cash

        # Beregn max drawdown i perioden
        max_dd = _compute_drawdown(normalized).min() * 100

        # Simuler med stop-loss
        if use_stop_loss:
            portfolio, _ , _ = _simulate_portfolio(
                close, pd.Series(False, index=close.index),
                pd.Series(False, index=close.index),
                initial_cash, stop_loss, take_profit=999,
            )
            pf_series = pd.Series(portfolio, index=close.index)
            sl_return = (pf_series.iloc[-1] / initial_cash - 1) * 100
        else:
            pf_series = normalized
            sl_return = (normalized.iloc[-1] / initial_cash - 1) * 100

        bh_return = (normalized.iloc[-1] / initial_cash - 1) * 100

        results.append({
            "Symbol": sym,
            "Buy & Hold afkast": f"{bh_return:.1f}%",
            "Med stop-loss": f"{sl_return:.1f}%" if use_stop_loss else "–",
            "Max Drawdown": f"{max_dd:.1f}%",
            "Slutværdi (B&H)": f"${normalized.iloc[-1]:,.0f}",
        })

        color = colors[i % len(colors)]
        fig.add_trace(go.Scatter(
            x=close.index, y=normalized,
            name=f"{sym} (Buy & Hold)",
            line=dict(color=color, width=2),
        ))
        if use_stop_loss:
            fig.add_trace(go.Scatter(
                x=pf_series.index, y=pf_series,
                name=f"{sym} (med {stop_loss:.0%} stop-loss)",
                line=dict(color=color, width=1.5, dash="dot"),
            ))

    fig.add_hline(
        y=initial_cash, line_dash="dash",
        line_color="gray", annotation_text="Startkapital",
    )
    fig.update_layout(
        title=f"{crisis_name} — porteføljeudvikling",
        yaxis_title="Porteføljeværdi (USD)",
        hovermode="x unified",
        margin=dict(l=0, r=0, t=40, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        pd.DataFrame(results),
        use_container_width=True,
        hide_index=True,
    )

    if use_stop_loss:
        st.info(
            f"Stop-loss på {stop_loss:.0%} aktiveres automatisk når en position falder "
            f"med det angivne beløb. I en krise kan kursen falde hurtigere end "
            f"daglige stop-loss-tjek, så det faktiske tab kan være lidt højere."
        )


# ------------------------------------------------------------------ #
#  Hjælpefunktioner                                                   #
# ------------------------------------------------------------------ #

def _simulate_portfolio(
    close: pd.Series,
    entries: pd.Series,
    exits: pd.Series,
    initial_cash: float,
    stop_loss: float,
    take_profit: float,
) -> tuple[list[float], list[float], list[float]]:
    """Simpel porteføljesimulering med stop-loss og take-profit."""
    cash = initial_cash
    shares = 0.0
    entry_price = 0.0
    pf_values = []
    trade_pnl = []
    entry_prices = []

    for i, (date, price) in enumerate(close.items()):
        # Stop-loss/take-profit check
        if shares > 0 and entry_price > 0:
            change = (price - entry_price) / entry_price
            if change <= -stop_loss or change >= take_profit:
                cash = shares * price
                trade_pnl.append(cash - (shares * entry_price))
                shares = 0.0
                entry_price = 0.0

        # Indgangssignal
        if entries.iloc[i] and shares == 0 and cash > 0:
            shares = cash / price
            entry_price = price
            entry_prices.append(price)
            cash = 0.0

        # Udgangssignal
        elif exits.iloc[i] and shares > 0:
            cash = shares * price
            trade_pnl.append(cash - (shares * entry_price))
            shares = 0.0
            entry_price = 0.0

        pf_values.append(cash + shares * price)

    return pf_values, trade_pnl, entry_prices


def _compute_drawdown(pf: pd.Series) -> pd.Series:
    """Beregn løbende drawdown."""
    rolling_max = pf.cummax()
    return (pf - rolling_max) / rolling_max


def _compute_sharpe(pf: pd.Series, risk_free: float = 0.04) -> float:
    """Beregn annualiseret Sharpe ratio."""
    returns = pf.pct_change().dropna()
    if returns.std() == 0:
        return 0.0
    excess = returns.mean() - risk_free / 252
    return float(excess / returns.std() * np.sqrt(252))
