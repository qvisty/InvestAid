"""
InvestAid - Risk Manager
Validerer alle ordrer inden de sendes til broker.
Implementerer stop-loss, take-profit, positionsgrænser og daglig tabsgrænse.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RiskCheckResult:
    approved: bool
    reason: str = ""
    adjusted_qty: Optional[float] = None  # Evt. reduceret antal


class RiskManager:
    """
    Risikokontrol for alle handler.

    Kontrollerer:
    1. Max portefølje-eksponering (max_portfolio_value)
    2. Max position størrelse (max_position_pct)
    3. Stop-loss pr. position
    4. Take-profit pr. position
    5. Max daglig tabsgrænse
    """

    def __init__(
        self,
        max_portfolio_value: float = 5000.0,
        max_position_pct: float = 0.05,
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.15,
        max_daily_loss_pct: float = 0.02,
    ):
        self.max_portfolio_value = max_portfolio_value
        self.max_position_pct = max_position_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_daily_loss_pct = max_daily_loss_pct

        # Daglig tabssporing
        self._daily_loss: float = 0.0
        self._daily_loss_date: date = date.today()
        self._trading_halted: bool = False

    def _reset_daily_if_new_day(self) -> None:
        today = date.today()
        if today != self._daily_loss_date:
            self._daily_loss = 0.0
            self._daily_loss_date = today
            self._trading_halted = False
            logger.info("Daglig tabssporing nulstillet (ny handelsdag)")

    def register_loss(self, loss_amount: float, portfolio_value: float) -> None:
        """
        Registrer et realiseret tab for at opdatere daglig tabssporing.
        Kald denne metode når en position lukkes med tab.
        """
        self._reset_daily_if_new_day()
        self._daily_loss += abs(loss_amount)

        daily_loss_pct = self._daily_loss / portfolio_value if portfolio_value > 0 else 0

        if daily_loss_pct >= self.max_daily_loss_pct:
            self._trading_halted = True
            logger.warning(
                f"DAGLIG TABSGRÆNSE NÅT: {daily_loss_pct:.1%} "
                f"(grænse: {self.max_daily_loss_pct:.1%}). "
                f"Al handel stoppet for i dag."
            )

    def check_buy_order(
        self,
        symbol: str,
        proposed_qty: float,
        current_price: float,
        portfolio_value: float,
        existing_position_value: float = 0.0,
    ) -> RiskCheckResult:
        """
        Valider om en købs-ordre er inden for risikogrænserne.

        Args:
            symbol: Symbol der handles
            proposed_qty: Ønsket antal aktier
            current_price: Nuværende pris
            portfolio_value: Samlet porteføljeværdi
            existing_position_value: Nuværende position i dette symbol (USD)

        Returns:
            RiskCheckResult med godkendelse og evt. justeret antal
        """
        self._reset_daily_if_new_day()

        # Check: handel stoppet for dagen
        if self._trading_halted:
            return RiskCheckResult(
                approved=False,
                reason=f"Handel stoppet: daglig tabsgrænse ({self.max_daily_loss_pct:.1%}) nået",
            )

        # Check: max porteføljeværdi
        effective_portfolio = min(portfolio_value, self.max_portfolio_value)
        order_value = proposed_qty * current_price
        total_new_position = existing_position_value + order_value

        # Check: max position størrelse
        max_position_value = effective_portfolio * self.max_position_pct
        if total_new_position > max_position_value:
            allowed_additional = max_position_value - existing_position_value
            if allowed_additional <= 0:
                return RiskCheckResult(
                    approved=False,
                    reason=(
                        f"Max position ({self.max_position_pct:.0%}) for {symbol} allerede nået. "
                        f"Nuværende: ${existing_position_value:.0f}, Max: ${max_position_value:.0f}"
                    ),
                )
            # Reducer ordren til hvad der er tilladt
            adjusted_qty = allowed_additional / current_price
            logger.info(
                f"[RiskManager] {symbol}: Ordre reduceret fra {proposed_qty:.2f} "
                f"til {adjusted_qty:.2f} aktier (position-grænse)"
            )
            return RiskCheckResult(
                approved=True,
                reason=f"Ordre reduceret til max position ({self.max_position_pct:.0%})",
                adjusted_qty=adjusted_qty,
            )

        return RiskCheckResult(approved=True, reason="OK")

    def check_stop_loss(
        self,
        symbol: str,
        avg_entry_price: float,
        current_price: float,
    ) -> bool:
        """
        Check om en position skal lukkes pga. stop-loss.

        Returns:
            True hvis stop-loss er nået og positionen skal sælges
        """
        if avg_entry_price <= 0:
            return False

        loss_pct = (avg_entry_price - current_price) / avg_entry_price

        if loss_pct >= self.stop_loss_pct:
            logger.warning(
                f"[RiskManager] STOP-LOSS: {symbol} er faldet {loss_pct:.1%} "
                f"(grænse: {self.stop_loss_pct:.1%}). Sælger."
            )
            return True
        return False

    def check_take_profit(
        self,
        symbol: str,
        avg_entry_price: float,
        current_price: float,
    ) -> bool:
        """
        Check om en position skal lukkes pga. take-profit.

        Returns:
            True hvis take-profit er nået og positionen skal sælges
        """
        if avg_entry_price <= 0:
            return False

        gain_pct = (current_price - avg_entry_price) / avg_entry_price

        if gain_pct >= self.take_profit_pct:
            logger.info(
                f"[RiskManager] TAKE-PROFIT: {symbol} er steget {gain_pct:.1%} "
                f"(mål: {self.take_profit_pct:.1%}). Tager gevinst."
            )
            return True
        return False

    def check_all_positions(
        self,
        positions: list,
    ) -> list[tuple[str, str]]:
        """
        Gennemgå alle åbne positioner for stop-loss og take-profit.

        Args:
            positions: Liste af Position objekter fra AlpacaClient

        Returns:
            Liste af (symbol, årsag) tupler for positioner der skal lukkes
        """
        to_close = []
        for position in positions:
            if self.check_stop_loss(
                position.symbol,
                position.avg_entry_price,
                position.current_price,
            ):
                to_close.append((position.symbol, "stop_loss"))
            elif self.check_take_profit(
                position.symbol,
                position.avg_entry_price,
                position.current_price,
            ):
                to_close.append((position.symbol, "take_profit"))
        return to_close

    def get_max_buy_notional(
        self,
        portfolio_value: float,
        existing_position_value: float = 0.0,
    ) -> float:
        """
        Beregn det maksimale beløb (USD) der kan bruges til én ny position.
        """
        effective_portfolio = min(portfolio_value, self.max_portfolio_value)
        max_position = effective_portfolio * self.max_position_pct
        return max(0.0, max_position - existing_position_value)

    @property
    def is_trading_halted(self) -> bool:
        self._reset_daily_if_new_day()
        return self._trading_halted

    def get_status(self) -> dict:
        """Returnér risikostatus som dict (til dashboard)"""
        self._reset_daily_if_new_day()
        return {
            "trading_halted": self._trading_halted,
            "daily_loss": self._daily_loss,
            "max_portfolio_value": self.max_portfolio_value,
            "max_position_pct": self.max_position_pct,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "max_daily_loss_pct": self.max_daily_loss_pct,
        }
