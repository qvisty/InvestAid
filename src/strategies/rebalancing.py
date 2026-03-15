"""
InvestAid - Portfolio Rebalancing Strategy
Bruger PyPortfolioOpt til at beregne optimale porteføljevægte og rebalancere.

Understøtter:
- Hierachical Risk Parity (HRP) - robust, ingen kovarians-inversion
- Efficient Frontier (Mean-Variance) - klassisk Markowitz optimering
- Equal Weight - simpel ligevægtig fordeling
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from .base import BaseStrategy, Signal, SignalType

logger = logging.getLogger(__name__)


class RebalancingStrategy(BaseStrategy):
    """
    Portefølje-rebalancering med PyPortfolioOpt.

    Parametre:
        method: "hrp" (default), "efficient_frontier", eller "equal_weight"
        rebalancing_interval_days: Dage mellem rebalancering (default: 30)
        min_weight: Minimum vægt per aktie (default: 0.02 = 2%)
        max_weight: Maximum vægt per aktie (default: 0.40 = 40%)
    """

    def __init__(
        self,
        method: str = "hrp",
        rebalancing_interval_days: int = 30,
        min_weight: float = 0.02,
        max_weight: float = 0.40,
    ):
        super().__init__("Portfolio Rebalancing")
        self.method = method
        self.rebalancing_interval_days = rebalancing_interval_days
        self.min_weight = min_weight
        self.max_weight = max_weight
        self._last_rebalance: Optional[datetime] = None
        self._target_weights: dict[str, float] = {}

    def _should_rebalance(self) -> bool:
        """Tjek om det er tid til at rebalancere"""
        if self._last_rebalance is None:
            return True
        days_since = (datetime.now() - self._last_rebalance).days
        return days_since >= self.rebalancing_interval_days

    def _compute_hrp_weights(self, returns: pd.DataFrame) -> dict[str, float]:
        """Beregn HRP-vægte (Hierarchical Risk Parity)"""
        try:
            from pypfopt import HRPOpt

            hrp = HRPOpt(returns=returns)
            weights = hrp.optimize()
            return {k: v for k, v in weights.items() if v > 0.001}
        except ImportError:
            logger.warning("PyPortfolioOpt ikke installeret - bruger equal weight")
            return self._compute_equal_weights(list(returns.columns))
        except Exception as e:
            logger.error(f"Fejl ved HRP beregning: {e}")
            return self._compute_equal_weights(list(returns.columns))

    def _compute_efficient_frontier_weights(
        self,
        returns: pd.DataFrame,
    ) -> dict[str, float]:
        """Beregn Efficient Frontier Max Sharpe vægte"""
        try:
            from pypfopt import EfficientFrontier, expected_returns, risk_models

            mu = expected_returns.mean_historical_return(returns, returns_data=True, frequency=252)
            cov = risk_models.sample_cov(returns, returns_data=True, frequency=252)

            ef = EfficientFrontier(mu, cov, weight_bounds=(self.min_weight, self.max_weight))
            weights = ef.max_sharpe(risk_free_rate=0.04)
            cleaned = ef.clean_weights(cutoff=0.01)
            return dict(cleaned)
        except ImportError:
            logger.warning("PyPortfolioOpt ikke installeret - bruger equal weight")
            return self._compute_equal_weights(list(returns.columns))
        except Exception as e:
            logger.error(f"Fejl ved Efficient Frontier beregning: {e}")
            return self._compute_equal_weights(list(returns.columns))

    def _compute_equal_weights(self, symbols: list[str]) -> dict[str, float]:
        """Simpel ligevægtig fordeling"""
        weight = 1.0 / len(symbols)
        return {s: weight for s in symbols}

    def compute_target_weights(self, data: dict[str, pd.DataFrame]) -> dict[str, float]:
        """
        Beregn target-vægte for porteføljen.
        Returnerer dict med symbol -> vægt (summer til 1.0)
        """
        if len(data) < 2:
            return self._compute_equal_weights(list(data.keys()))

        # Byg returns DataFrame
        close_prices = {}
        for symbol, df in data.items():
            if not df.empty and len(df) > 30:
                close_prices[symbol] = df["Close"]

        if len(close_prices) < 2:
            return self._compute_equal_weights(list(data.keys()))

        prices_df = pd.DataFrame(close_prices).dropna()
        returns = prices_df.pct_change().dropna()

        if returns.empty or len(returns) < 20:
            return self._compute_equal_weights(list(data.keys()))

        if self.method == "hrp":
            weights = self._compute_hrp_weights(returns)
        elif self.method == "efficient_frontier":
            weights = self._compute_efficient_frontier_weights(returns)
        else:
            weights = self._compute_equal_weights(list(close_prices.keys()))

        # Normaliser til at summe til 1.0
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

        return weights

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> dict[str, Signal]:
        """
        Generer rebalancerings-signaler.
        Sammenligner nuværende positioner med target-vægte og foreslår justeringer.
        """
        if not self._should_rebalance():
            return {}

        logger.info(f"[{self.name}] Beregner nye porteføljevægte ({self.method.upper()})...")

        target_weights = self.compute_target_weights(data)
        self._target_weights = target_weights
        self._last_rebalance = datetime.now()

        if not target_weights:
            return {}

        # Generer BUY signaler for alle symboler i target
        # (Portfolio Manager tager sig af den faktiske rebalancering)
        signals = {}
        for symbol, weight in target_weights.items():
            if symbol in data and not data[symbol].empty:
                current_price = float(data[symbol]["Close"].iloc[-1])
                signals[symbol] = Signal(
                    symbol=symbol,
                    signal=SignalType.BUY,
                    strength=weight,  # Brug weight som styrke
                    price=current_price,
                    strategy=self.name,
                    notes=f"Target vægt: {weight:.1%} ({self.method.upper()})",
                )
                logger.info(f"  {symbol}: target {weight:.1%}")

        return signals

    def get_target_weights(self) -> dict[str, float]:
        """Returner de senest beregnede target-vægte"""
        return self._target_weights.copy()
