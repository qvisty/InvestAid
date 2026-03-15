"""
InvestAid - Portfolio Manager
Koordinerer strategier, risikostyring og broker til at eksekvere handler.
Dette er systemets hjerne.
"""

import logging
from typing import Optional

from .broker.alpaca_client import AlpacaClient, Position, create_client_from_config
from .config import AppConfig, get_config
from .data.market_data import get_historical_data, get_multiple_symbols
from .database import init_db, save_portfolio_snapshot, save_signal, save_trade
from .risk_manager import RiskManager
from .strategies.base import Signal, SignalType
from .strategies.momentum import MomentumStrategy
from .strategies.rebalancing import RebalancingStrategy
from .strategies.trend_following import TrendFollowingStrategy

logger = logging.getLogger(__name__)


class PortfolioManager:
    """
    Koordinerer hele trading-processen:
    1. Henter markedsdata
    2. Kører aktive strategier
    3. Kombinerer signaler
    4. Validerer mod risikoregler
    5. Eksekverer handler via broker
    6. Logger alt til database
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        broker: Optional[AlpacaClient] = None,
    ):
        self.config = config or get_config()
        self.broker = broker or create_client_from_config()

        self.risk_manager = RiskManager(
            max_portfolio_value=self.config.risk.max_portfolio_value,
            max_position_pct=self.config.risk.max_position_pct,
            stop_loss_pct=self.config.risk.stop_loss_pct,
            take_profit_pct=self.config.risk.take_profit_pct,
            max_daily_loss_pct=self.config.risk.max_daily_loss_pct,
        )

        self.strategies = self._init_strategies()
        init_db()

        mode = "PAPER" if self.config.is_paper_mode else "LIVE"
        logger.info(f"PortfolioManager initialiseret ({mode} mode)")
        logger.info(f"Watchlist: {self.config.watchlist.symbols}")

    def _init_strategies(self) -> list:
        strategies = []
        cfg = self.config.strategy

        if cfg.trend_following_enabled:
            strategies.append(TrendFollowingStrategy(
                fast_period=cfg.ema_fast_period,
                slow_period=cfg.ema_slow_period,
            ))

        if cfg.momentum_enabled:
            strategies.append(MomentumStrategy(
                rsi_period=cfg.rsi_period,
                oversold=cfg.rsi_oversold,
                overbought=cfg.rsi_overbought,
            ))

        if cfg.rebalancing_enabled:
            strategies.append(RebalancingStrategy(
                method="hrp",
                rebalancing_interval_days=cfg.rebalancing_interval_days,
            ))

        logger.info(f"Aktive strategier: {[s.get_name() for s in strategies]}")
        return strategies

    def fetch_market_data(self) -> dict:
        """Hent markedsdata for alle watchlist-symboler"""
        symbols = self.config.watchlist.symbols
        logger.info(f"Henter markedsdata for {len(symbols)} symboler...")
        data = get_multiple_symbols(symbols, period="3mo", interval="1d")
        logger.info(f"Hentet data for {len(data)}/{len(symbols)} symboler")
        return data

    def generate_combined_signals(self, data: dict) -> dict[str, Signal]:
        """
        Kør alle aktive strategier og kombiner signalerne.
        Ved konflikterende signaler vinder det stærkeste signal.
        """
        all_signals: dict[str, list[Signal]] = {}

        for strategy in self.strategies:
            try:
                signals = strategy.generate_signals(data)
                for symbol, signal in signals.items():
                    if symbol not in all_signals:
                        all_signals[symbol] = []
                    all_signals[symbol].append(signal)

                    # Gem signal til database
                    save_signal(
                        symbol=symbol,
                        strategy=strategy.get_name(),
                        signal=signal.signal.value,
                        strength=signal.strength,
                        price=signal.price,
                        notes=signal.notes,
                    )
            except Exception as e:
                logger.error(f"Fejl i strategi {strategy.get_name()}: {e}")

        # Kombiner signaler: vælg det med højeste styrke per symbol
        combined: dict[str, Signal] = {}
        for symbol, signals in all_signals.items():
            buy_signals = [s for s in signals if s.signal == SignalType.BUY]
            sell_signals = [s for s in signals if s.signal == SignalType.SELL]

            # Vælg den type der har flest/stærkeste signaler
            buy_strength = sum(s.strength for s in buy_signals)
            sell_strength = sum(s.strength for s in sell_signals)

            if buy_strength > sell_strength and buy_strength > 0.3:
                best = max(buy_signals, key=lambda s: s.strength)
                combined[symbol] = best
            elif sell_strength > buy_strength and sell_strength > 0.3:
                best = max(sell_signals, key=lambda s: s.strength)
                combined[symbol] = best

        logger.info(f"Kombinerede signaler: {len(combined)} aktionspunkter")
        return combined

    def execute_signals(self, signals: dict[str, Signal]) -> list[str]:
        """
        Eksekvér godkendte handelssignaler.

        Returns:
            Liste over symboler hvor handler blev eksekveret
        """
        if not self.broker.is_connected:
            logger.warning("Broker ikke forbundet - kan ikke eksekvere handler")
            return []

        if self.risk_manager.is_trading_halted:
            logger.warning("Handel stoppet pga. daglig tabsgrænse")
            return []

        account = self.broker.get_account()
        if not account:
            logger.error("Kan ikke hente kontosaldo - afbryder")
            return []

        portfolio_value = account.portfolio_value
        positions = {p.symbol: p for p in self.broker.get_positions()}
        executed = []

        # Check stop-loss/take-profit for eksisterende positioner
        self._check_and_close_risk_positions(
            list(positions.values()), portfolio_value
        )

        # Eksekvér nye signaler
        for symbol, signal in signals.items():
            try:
                symbol_clean = symbol.replace("/", "")
                existing_pos = positions.get(symbol, positions.get(symbol_clean))
                existing_value = existing_pos.market_value if existing_pos else 0.0

                if signal.signal == SignalType.BUY:
                    success = self._execute_buy(
                        symbol, signal, portfolio_value, existing_value
                    )
                elif signal.signal == SignalType.SELL:
                    success = self._execute_sell(symbol, signal, existing_pos)
                else:
                    continue

                if success:
                    executed.append(symbol)

            except Exception as e:
                logger.error(f"Fejl ved eksekvering af signal for {symbol}: {e}")

        # Gem portfolio snapshot
        if account:
            invested = portfolio_value - account.cash
            save_portfolio_snapshot(
                total_value=portfolio_value,
                cash=account.cash,
                invested=invested,
                paper=self.config.is_paper_mode,
            )

        return executed

    def _execute_buy(
        self,
        symbol: str,
        signal: Signal,
        portfolio_value: float,
        existing_position_value: float,
    ) -> bool:
        """Eksekvér en købs-ordre med risikostyring"""
        max_notional = self.risk_manager.get_max_buy_notional(
            portfolio_value, existing_position_value
        )

        if max_notional < 1.0:
            logger.info(f"Skip {symbol}: ingen plads til ny position (max: ${max_notional:.2f})")
            return False

        # Brug signal-styrke til at skalere ordrestørrelsen
        notional = max_notional * signal.strength
        notional = max(1.0, round(notional, 2))

        risk_check = self.risk_manager.check_buy_order(
            symbol=symbol,
            proposed_qty=1,  # Dummy, vi bruger notional
            current_price=signal.price or 1.0,
            portfolio_value=portfolio_value,
            existing_position_value=existing_position_value,
        )

        if not risk_check.approved:
            logger.info(f"Skip {symbol}: {risk_check.reason}")
            return False

        order = self.broker.place_market_order(
            symbol=symbol,
            side="buy",
            qty=0,  # Ikke brugt når notional er sat
            notional=notional,
        )

        if order:
            save_trade(
                symbol=symbol,
                side="buy",
                qty=notional / (signal.price or 1.0),
                price=signal.price,
                order_id=order.id,
                strategy=signal.strategy,
                paper=self.config.is_paper_mode,
                status=order.status,
            )
            logger.info(f"KØB eksekveret: {symbol} for ${notional:.2f}")
            return True
        return False

    def _execute_sell(
        self,
        symbol: str,
        signal: Signal,
        position: Optional[Position],
    ) -> bool:
        """Eksekvér en salgs-ordre"""
        if not position:
            logger.debug(f"Skip SELL {symbol}: ingen åben position")
            return False

        order = self.broker.place_market_order(
            symbol=symbol,
            side="sell",
            qty=position.qty,
        )

        if order:
            save_trade(
                symbol=symbol,
                side="sell",
                qty=position.qty,
                price=signal.price,
                order_id=order.id,
                strategy=signal.strategy,
                paper=self.config.is_paper_mode,
                status=order.status,
            )
            if position.unrealized_pl < 0:
                account = self.broker.get_account()
                if account:
                    self.risk_manager.register_loss(
                        abs(position.unrealized_pl), account.portfolio_value
                    )
            logger.info(f"SÆLG eksekveret: {symbol} ({position.qty} stk)")
            return True
        return False

    def _check_and_close_risk_positions(
        self, positions: list[Position], portfolio_value: float
    ) -> None:
        """Check og luk positioner der rammer stop-loss eller take-profit"""
        to_close = self.risk_manager.check_all_positions(positions)
        for symbol, reason in to_close:
            pos = next((p for p in positions if p.symbol == symbol), None)
            if pos:
                dummy_signal = Signal(
                    symbol=symbol,
                    signal=SignalType.SELL,
                    strength=1.0,
                    price=pos.current_price,
                    strategy=f"risk_manager_{reason}",
                    notes=reason,
                )
                self._execute_sell(symbol, dummy_signal, pos)

    def run_cycle(self) -> dict:
        """
        Kør én komplet trading-cyklus:
        1. Hent data
        2. Generer signaler
        3. Eksekvér handler

        Returns:
            Opsummering af cyklussen
        """
        logger.info("=== Trading-cyklus starter ===")

        data = self.fetch_market_data()
        if not data:
            logger.warning("Ingen markedsdata - afbryder cyklus")
            return {"status": "no_data"}

        signals = self.generate_combined_signals(data)
        executed = self.execute_signals(signals)

        summary = {
            "status": "ok",
            "symbols_analyzed": len(data),
            "signals_generated": len(signals),
            "trades_executed": len(executed),
            "executed_symbols": executed,
            "paper_mode": self.config.is_paper_mode,
        }

        logger.info(
            f"=== Cyklus afsluttet: "
            f"{len(signals)} signaler, "
            f"{len(executed)} handler eksekveret ==="
        )
        return summary

    def get_portfolio_status(self) -> dict:
        """Hent samlet porteføljestatus (til dashboard)"""
        if not self.broker.is_connected:
            return {"connected": False}

        account = self.broker.get_account()
        positions = self.broker.get_positions()
        risk_status = self.risk_manager.get_status()

        return {
            "connected": True,
            "paper_mode": self.config.is_paper_mode,
            "account": {
                "equity": account.equity if account else 0,
                "cash": account.cash if account else 0,
                "portfolio_value": account.portfolio_value if account else 0,
                "buying_power": account.buying_power if account else 0,
            },
            "positions": [
                {
                    "symbol": p.symbol,
                    "qty": p.qty,
                    "avg_entry_price": p.avg_entry_price,
                    "current_price": p.current_price,
                    "market_value": p.market_value,
                    "unrealized_pl": p.unrealized_pl,
                    "unrealized_plpc": p.unrealized_plpc,
                }
                for p in positions
            ],
            "risk": risk_status,
        }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    manager = PortfolioManager()
    summary = manager.run_cycle()
    print(f"\nCyklus-opsummering: {summary}")
