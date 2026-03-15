"""
InvestAid - Trend Following Strategy
Bruger EMA crossover og MACD til at identificere trends.

Logik:
- KØB: Hurtig EMA krydser over langsom EMA (bullish crossover)
- SÆlG: Hurtig EMA krydser under langsom EMA (bearish crossover)
- Bekræftes af MACD signal for højere tillid
"""

import logging
from typing import Optional

import pandas as pd
import pandas_ta as ta

from .base import BaseStrategy, Signal, SignalType
from .filters import adx_filter, regime_filter

logger = logging.getLogger(__name__)


class TrendFollowingStrategy(BaseStrategy):
    """
    EMA Crossover + MACD Trend Following Strategi.

    Parametre:
        fast_period: Perioder for hurtig EMA (default: 12)
        slow_period: Perioder for langsom EMA (default: 26)
        macd_fast: MACD hurtig periode (default: 12)
        macd_slow: MACD langsom periode (default: 26)
        macd_signal: MACD signal periode (default: 9)
        require_macd_confirm: Kræv MACD-bekræftelse (default: True)
    """

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        require_macd_confirm: bool = True,
        use_regime_filter: bool = True,
        use_adx_filter: bool = True,
        adx_threshold: float = 22.0,
    ):
        super().__init__("EMA Crossover + MACD")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.require_macd_confirm = require_macd_confirm
        self.use_regime_filter = use_regime_filter
        self.use_adx_filter = use_adx_filter
        self.adx_threshold = adx_threshold

    def _compute_signals(self, df: pd.DataFrame) -> Optional[Signal]:
        """Beregn signal for ét symbol"""
        if len(df) < self.slow_period + 5:
            return None

        close = df["Close"].copy()

        # EMA beregning
        ema_fast = ta.ema(close, length=self.fast_period)
        ema_slow = ta.ema(close, length=self.slow_period)

        if ema_fast is None or ema_slow is None:
            return None

        # MACD beregning
        macd_df = ta.macd(
            close,
            fast=self.macd_fast,
            slow=self.macd_slow,
            signal=self.macd_signal,
        )

        if macd_df is None or macd_df.empty:
            return None

        # Seneste og forrige værdier
        ema_fast_now = ema_fast.iloc[-1]
        ema_fast_prev = ema_fast.iloc[-2]
        ema_slow_now = ema_slow.iloc[-1]
        ema_slow_prev = ema_slow.iloc[-2]

        macd_col = [c for c in macd_df.columns if c.startswith("MACD_") and "signal" not in c.lower() and "h" not in c.lower()]
        signal_col = [c for c in macd_df.columns if "MACDs" in c]

        if not macd_col or not signal_col:
            return None

        macd_now = macd_df[macd_col[0]].iloc[-1]
        macd_signal_now = macd_df[signal_col[0]].iloc[-1]

        # Detekter EMA crossover
        bullish_cross = (ema_fast_prev <= ema_slow_prev) and (ema_fast_now > ema_slow_now)
        bearish_cross = (ema_fast_prev >= ema_slow_prev) and (ema_fast_now < ema_slow_now)

        # MACD bekræftelse
        macd_bullish = macd_now > macd_signal_now
        macd_bearish = macd_now < macd_signal_now

        current_price = float(close.iloc[-1])

        if bullish_cross:
            if not self.require_macd_confirm or macd_bullish:
                # Regime-filter: kun BUY i bull-marked (pris over 200-dages MA)
                if self.use_regime_filter and not regime_filter(close):
                    logger.debug(
                        f"BUY-signal blokeret af regime-filter (bear-marked): "
                        f"pris under 200-dages MA"
                    )
                    return None

                # ADX-filter: kun trend-following i trendende markeder
                if self.use_adx_filter and not adx_filter(df, threshold=self.adx_threshold):
                    logger.debug(
                        f"BUY-signal blokeret af ADX-filter: "
                        f"ADX < {self.adx_threshold} (sideværts marked)"
                    )
                    return None

                strength = 0.8 if macd_bullish else 0.5
                filter_notes = []
                if self.use_regime_filter:
                    filter_notes.append("bull-regime")
                if self.use_adx_filter:
                    filter_notes.append(f"ADX≥{self.adx_threshold}")
                filter_str = " + ".join(filter_notes)
                return Signal(
                    symbol="",
                    signal=SignalType.BUY,
                    strength=strength,
                    price=current_price,
                    strategy=self.name,
                    notes=f"EMA{self.fast_period} krydsede over EMA{self.slow_period}"
                          + (" + MACD bekræftet" if macd_bullish else "")
                          + (f" [{filter_str}]" if filter_str else ""),
                )

        elif bearish_cross:
            if not self.require_macd_confirm or macd_bearish:
                strength = 0.8 if macd_bearish else 0.5
                return Signal(
                    symbol="",
                    signal=SignalType.SELL,
                    strength=strength,
                    price=current_price,
                    strategy=self.name,
                    notes=f"EMA{self.fast_period} krydsede under EMA{self.slow_period}"
                          + (" + MACD bekræftet" if macd_bearish else ""),
                )

        return None

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> dict[str, Signal]:
        signals = {}
        for symbol, df in data.items():
            try:
                signal = self._compute_signals(df)
                if signal is not None:
                    signal.symbol = symbol
                    signals[symbol] = signal
                    logger.info(
                        f"[{self.name}] {symbol}: {signal.signal.value} "
                        f"(styrke: {signal.strength:.1%}) - {signal.notes}"
                    )
            except Exception as e:
                logger.error(f"Fejl ved beregning af signal for {symbol}: {e}")
        return signals
