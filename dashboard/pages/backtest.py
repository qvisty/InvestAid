"""
InvestAid Dashboard - Backtesting
Kør historiske tests af strategier med VectorBT.
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.market_data import get_historical_data


def show_backtest() -> None:
    st.header("Backtesting")
    st.caption("Test strategier på historiske data inden du bruger rigtige penge.")

    # Indstillinger
    col1, col2, col3 = st.columns(3)
    with col1:
        symbol = st.text_input("Symbol", value="SPY", help="F.eks. SPY, QQQ, GLD, AAPL")
    with col2:
        period = st.selectbox("Periode", ["6mo", "1y", "2y", "5y"], index=1)
    with col3:
        strategy = st.selectbox(
            "Strategi",
            ["EMA Crossover", "RSI Momentum", "Kombineret"],
        )

    col4, col5 = st.columns(2)
    with col4:
        fast_ema = st.slider("Hurtig EMA", 5, 50, 12)
    with col5:
        slow_ema = st.slider("Langsom EMA", 10, 200, 26)

    rsi_oversold = st.slider("RSI Oversold grænse", 10, 40, 30)
    rsi_overbought = st.slider("RSI Overbought grænse", 60, 90, 70)

    if st.button("Kør Backtest", type="primary"):
        with st.spinner(f"Henter data og kører backtest for {symbol}..."):
            _run_backtest(symbol, period, strategy, fast_ema, slow_ema, rsi_oversold, rsi_overbought)


def _run_backtest(
    symbol: str,
    period: str,
    strategy: str,
    fast_ema: int,
    slow_ema: int,
    rsi_oversold: int,
    rsi_overbought: int,
) -> None:
    df = get_historical_data(symbol.upper(), period=period)

    if df.empty:
        st.error(f"Ingen data for {symbol}. Tjek symbolet og prøv igen.")
        return

    try:
        import vectorbt as vbt
        import pandas_ta as ta

        close = df["Close"]

        if strategy == "EMA Crossover":
            entries, exits = _ema_signals(close, fast_ema, slow_ema)
            strategy_label = f"EMA({fast_ema}/{slow_ema})"
        elif strategy == "RSI Momentum":
            entries, exits = _rsi_signals(close, rsi_oversold, rsi_overbought)
            strategy_label = f"RSI({rsi_oversold}/{rsi_overbought})"
        else:
            ema_entries, ema_exits = _ema_signals(close, fast_ema, slow_ema)
            rsi_entries, rsi_exits = _rsi_signals(close, rsi_oversold, rsi_overbought)
            entries = ema_entries | rsi_entries
            exits = ema_exits | rsi_exits
            strategy_label = "Kombineret"

        # Kør backtest med VectorBT
        portfolio = vbt.Portfolio.from_signals(
            close=close,
            entries=entries,
            exits=exits,
            init_cash=10_000,
            fees=0.001,  # 0.1% kurtage
            freq="D",
        )

        # Metrics
        stats = portfolio.stats()
        _show_results(portfolio, stats, close, strategy_label, symbol)

    except ImportError:
        st.warning("VectorBT ikke installeret. Kører simpel backtest...")
        _simple_backtest(df, symbol, fast_ema, slow_ema)
    except Exception as e:
        st.error(f"Fejl i backtest: {e}")


def _ema_signals(close: pd.Series, fast: int, slow: int):
    import pandas_ta as ta
    ema_fast = ta.ema(close, length=fast)
    ema_slow = ta.ema(close, length=slow)
    entries = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))
    exits = (ema_fast < ema_slow) & (ema_fast.shift(1) >= ema_slow.shift(1))
    return entries.fillna(False), exits.fillna(False)


def _rsi_signals(close: pd.Series, oversold: int, overbought: int):
    import pandas_ta as ta
    rsi = ta.rsi(close, length=14)
    entries = (rsi < oversold) & (rsi.shift(1) >= oversold)
    exits = (rsi > overbought) & (rsi.shift(1) <= overbought)
    return entries.fillna(False), exits.fillna(False)


def _show_results(portfolio, stats, close: pd.Series, strategy_label: str, symbol: str) -> None:
    st.success(f"Backtest færdig: {strategy_label} på {symbol}")

    # Nøgletal
    total_return = stats.get("Total Return [%]", 0)
    sharpe = stats.get("Sharpe Ratio", 0)
    max_dd = stats.get("Max Drawdown [%]", 0)
    win_rate = stats.get("Win Rate [%]", 0)
    num_trades = stats.get("# Trades", 0)
    buy_hold_return = ((close.iloc[-1] / close.iloc[0]) - 1) * 100

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        color = "normal" if total_return >= 0 else "inverse"
        st.metric("Samlet afkast", f"{total_return:.2f}%", delta_color=color)
    with col2:
        st.metric("Sharpe Ratio", f"{sharpe:.2f}",
                  help="Over 1.0 er godt, over 2.0 er fremragende")
    with col3:
        st.metric("Max Drawdown", f"{max_dd:.2f}%")
    with col4:
        st.metric("Win Rate", f"{win_rate:.1f}%")

    col5, col6 = st.columns(2)
    with col5:
        st.metric("Antal handler", int(num_trades))
    with col6:
        bh_color = "normal" if buy_hold_return >= 0 else "inverse"
        st.metric("Buy & Hold afkast", f"{buy_hold_return:.2f}%", delta_color=bh_color)

    # Performance graf
    st.subheader("Portfolio Værdi vs. Buy & Hold")
    try:
        pf_value = portfolio.value()
        bh_value = (close / close.iloc[0]) * 10_000

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=pf_value.index, y=pf_value,
            name=f"Strategi ({strategy_label})",
            line=dict(color="#00C851", width=2),
        ))
        fig.add_trace(go.Scatter(
            x=bh_value.index, y=bh_value,
            name="Buy & Hold",
            line=dict(color="#888888", width=1, dash="dash"),
        ))
        fig.update_layout(
            yaxis_title="Porteføljeværdi (USD)",
            hovermode="x unified",
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.warning(f"Kunne ikke vise graf: {e}")

    # Drawdown graf
    st.subheader("Drawdown")
    try:
        dd = portfolio.drawdown() * 100
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=dd.index, y=dd,
            fill="tozeroy",
            name="Drawdown %",
            line=dict(color="#FF4444"),
        ))
        fig2.update_layout(
            yaxis_title="Drawdown (%)",
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig2, use_container_width=True)
    except Exception:
        pass


def _simple_backtest(df: pd.DataFrame, symbol: str, fast_ema: int, slow_ema: int) -> None:
    """Simpel backtest uden VectorBT (fallback)"""
    import pandas_ta as ta

    close = df["Close"]
    ema_fast = ta.ema(close, length=fast_ema)
    ema_slow = ta.ema(close, length=slow_ema)

    initial_cash = 10_000
    cash = initial_cash
    shares = 0
    trades = 0

    for i in range(1, len(close)):
        if ema_fast.iloc[i] > ema_slow.iloc[i] and ema_fast.iloc[i-1] <= ema_slow.iloc[i-1]:
            if cash > 0:
                shares = cash / close.iloc[i]
                cash = 0
                trades += 1
        elif ema_fast.iloc[i] < ema_slow.iloc[i] and ema_fast.iloc[i-1] >= ema_slow.iloc[i-1]:
            if shares > 0:
                cash = shares * close.iloc[i]
                shares = 0
                trades += 1

    final_value = cash + shares * close.iloc[-1]
    total_return = (final_value / initial_cash - 1) * 100
    buy_hold = (close.iloc[-1] / close.iloc[0] - 1) * 100

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Samlet afkast", f"{total_return:.2f}%")
    with col2:
        st.metric("Buy & Hold", f"{buy_hold:.2f}%")
    with col3:
        st.metric("Antal handler", trades)
