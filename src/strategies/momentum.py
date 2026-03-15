"""
InvestAid - Momentum Strategy
Bruger RSI til at identificere overkøbte/oversolgte aktier.

Logik:
- KØB: RSI falder under oversold-grænsen og begynder at vende opad
- SÆlG: RSI stiger over overbought-grænsen og begynder at vende nedad
- Styrke afhænger af, hvor langt RSI er fra midterpunktet (50)
"""

import logging
from typing import Optional

import pandas as pd
import pandas_ta as ta

from .base import BaseStrategy, Signal, SignalType

logger = logging.getLogger(__name__)


class MomentumStrategy(BaseStrategy):
    """
    RSI-baseret Momentum Strategi.

    Parametre:
        rsi_period: RSI beregningsperiode (default: 14)
        oversold: Køb-signal under dette niveau (default: 30)
        overbought: Sælg-signal over dette niveau (default: 70)
        use_divergence: Inkluder RSI-divergens-analyse (default: False)
    """

    def __init__(
        self,
        rsi_period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        use_divergence: bool = False,
    ):
        super().__init__("RSI Momentum")
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.use_divergence = use_divergence

    def _compute_signals(self, df: pd.DataFrame) -> Optional[Signal]:
        """Beregn RSI signal for ét symbol"""
        if len(df) < self.rsi_period + 5:
            return None

        close = df["Close"].copy()
        rsi = ta.rsi(close, length=self.rsi_period)

        if rsi is None or rsi.isna().all():
            return None

        rsi_now = rsi.iloc[-1]
        rsi_prev = rsi.iloc[-2]
        current_price = float(close.iloc[-1])

        if pd.isna(rsi_now) or pd.isna(rsi_prev):
            return None

        # Oversold recovery: RSI var under oversold og vender nu opad
        oversold_recovery = (rsi_prev <= self.oversold) and (rsi_now > rsi_prev)

        # Overbought reversal: RSI var over overbought og vender nu nedad
        overbought_reversal = (rsi_prev >= self.overbought) and (rsi_now < rsi_prev)

        if oversold_recovery:
            # Styrke: jo lavere RSI, jo stærkere signal
            strength = min(1.0, (self.oversold - min(rsi_now, rsi_prev)) / self.oversold + 0.5)
            strength = max(0.3, min(1.0, strength))
            return Signal(
                symbol="",
                signal=SignalType.BUY,
                strength=strength,
                price=current_price,
                strategy=self.name,
                notes=f"RSI={rsi_now:.1f} vender opad fra oversold zone (<{self.oversold})",
            )

        elif overbought_reversal:
            # Styrke: jo højere RSI, jo stærkere signal
            strength = min(1.0, (max(rsi_now, rsi_prev) - self.overbought) / (100 - self.overbought) + 0.5)
            strength = max(0.3, min(1.0, strength))
            return Signal(
                symbol="",
                signal=SignalType.SELL,
                strength=strength,
                price=current_price,
                strategy=self.name,
                notes=f"RSI={rsi_now:.1f} vender nedad fra overbought zone (>{self.overbought})",
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
                        f"(RSI-styrke: {signal.strength:.1%}) - {signal.notes}"
                    )
            except Exception as e:
                logger.error(f"Fejl ved beregning af momentum signal for {symbol}: {e}")
        return signals
