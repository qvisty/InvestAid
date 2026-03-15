"""
InvestAid - Alpaca Broker Klient
Håndterer al kommunikation med Alpaca (paper og live trading).
Paper trading er default og anbefalet til at starte.
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Position:
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_plpc: float  # Procent


@dataclass
class AccountInfo:
    equity: float           # Samlet porteføljeværdi
    cash: float             # Likvide midler
    buying_power: float     # Tilgængelig købekraft
    portfolio_value: float
    paper: bool


@dataclass
class Order:
    id: str
    symbol: str
    side: str               # "buy" eller "sell"
    qty: float
    status: str
    filled_avg_price: Optional[float]


class AlpacaClient:
    """
    Alpaca trading klient.
    Bruger automatisk paper trading URL medmindre live_trading=True.
    """

    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self._trading_client = None
        self._data_client = None
        self._initialized = False

        if api_key and secret_key:
            self._init_clients()

    def _init_clients(self) -> None:
        try:
            from alpaca.trading.client import TradingClient

            self._trading_client = TradingClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=self.paper,
            )
            self._initialized = True
            mode = "PAPER" if self.paper else "LIVE"
            logger.info(f"Alpaca klient initialiseret ({mode} trading)")
        except ImportError:
            logger.error("alpaca-py ikke installeret. Kør: pip install alpaca-py")
        except Exception as e:
            logger.error(f"Fejl ved initialisering af Alpaca klient: {e}")

    @property
    def is_connected(self) -> bool:
        return self._initialized and self._trading_client is not None

    def get_account(self) -> Optional[AccountInfo]:
        """Hent kontooplysninger (saldo, købekraft etc.)"""
        if not self.is_connected:
            return None
        try:
            account = self._trading_client.get_account()
            return AccountInfo(
                equity=float(account.equity),
                cash=float(account.cash),
                buying_power=float(account.buying_power),
                portfolio_value=float(account.portfolio_value),
                paper=self.paper,
            )
        except Exception as e:
            logger.error(f"Fejl ved hentning af konto: {e}")
            return None

    def get_positions(self) -> list[Position]:
        """Hent alle åbne positioner"""
        if not self.is_connected:
            return []
        try:
            positions = self._trading_client.get_all_positions()
            result = []
            for p in positions:
                result.append(Position(
                    symbol=p.symbol,
                    qty=float(p.qty),
                    avg_entry_price=float(p.avg_entry_price),
                    current_price=float(p.current_price),
                    market_value=float(p.market_value),
                    unrealized_pl=float(p.unrealized_pl),
                    unrealized_plpc=float(p.unrealized_plpc),
                ))
            return result
        except Exception as e:
            logger.error(f"Fejl ved hentning af positioner: {e}")
            return []

    def get_position(self, symbol: str) -> Optional[Position]:
        """Hent en specifik åben position"""
        positions = self.get_positions()
        symbol_clean = symbol.replace("/", "")
        for p in positions:
            if p.symbol == symbol or p.symbol == symbol_clean:
                return p
        return None

    def place_market_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        notional: Optional[float] = None,
    ) -> Optional[Order]:
        """
        Afgiv en markedsordre.

        Args:
            symbol: Aktiesymbol (f.eks. "SPY", "BTC/USD")
            side: "buy" eller "sell"
            qty: Antal aktier (eller brug notional for beløb i USD)
            notional: Køb for X USD i stedet for et fast antal aktier

        Returns:
            Order objekt eller None ved fejl
        """
        if not self.is_connected:
            logger.error("Ikke forbundet til Alpaca")
            return None

        try:
            from alpaca.trading.enums import OrderSide, TimeInForce
            from alpaca.trading.requests import MarketOrderRequest

            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

            if notional is not None:
                # Køb for et bestemt beløb i USD (fractional shares)
                request = MarketOrderRequest(
                    symbol=symbol,
                    notional=round(notional, 2),
                    side=order_side,
                    time_in_force=TimeInForce.DAY,
                )
            else:
                request = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=order_side,
                    time_in_force=TimeInForce.DAY,
                )

            order = self._trading_client.submit_order(request)
            mode = "PAPER" if self.paper else "LIVE"
            logger.info(
                f"[{mode}] Ordre afgivet: {side.upper()} {qty or f'${notional}'} {symbol} "
                f"(ID: {order.id})"
            )

            return Order(
                id=str(order.id),
                symbol=order.symbol,
                side=side,
                qty=float(order.qty or 0),
                status=str(order.status),
                filled_avg_price=float(order.filled_avg_price) if order.filled_avg_price else None,
            )

        except Exception as e:
            logger.error(f"Fejl ved afgivelse af ordre for {symbol}: {e}")
            return None

    def cancel_all_orders(self) -> int:
        """Annuller alle åbne ordrer. Returns antal annullerede."""
        if not self.is_connected:
            return 0
        try:
            cancelled = self._trading_client.cancel_orders()
            count = len(cancelled) if cancelled else 0
            logger.info(f"Annullerede {count} åbne ordrer")
            return count
        except Exception as e:
            logger.error(f"Fejl ved annullering af ordrer: {e}")
            return 0

    def get_portfolio_history(self, period: str = "1M") -> Optional[dict]:
        """Hent porteføljehistorik (til P&L graf)"""
        if not self.is_connected:
            return None
        try:
            from alpaca.trading.requests import GetPortfolioHistoryRequest

            request = GetPortfolioHistoryRequest(period=period, timeframe="1D")
            history = self._trading_client.get_portfolio_history(request)
            return {
                "timestamps": history.timestamp,
                "equity": history.equity,
                "profit_loss": history.profit_loss,
                "profit_loss_pct": history.profit_loss_pct,
            }
        except Exception as e:
            logger.error(f"Fejl ved hentning af porteføljehistorik: {e}")
            return None


def create_client_from_config() -> AlpacaClient:
    """Opret Alpaca klient fra konfiguration"""
    from src.config import get_config

    cfg = get_config()
    return AlpacaClient(
        api_key=cfg.alpaca_api_key,
        secret_key=cfg.alpaca_secret_key,
        paper=cfg.is_paper_mode,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    client = create_client_from_config()
    if client.is_connected:
        account = client.get_account()
        if account:
            mode = "PAPER" if account.paper else "LIVE"
            print(f"\n=== Alpaca Konto ({mode}) ===")
            print(f"Porteføljeværdi: ${account.portfolio_value:,.2f}")
            print(f"Likvide midler:  ${account.cash:,.2f}")
            print(f"Købekraft:       ${account.buying_power:,.2f}")

        positions = client.get_positions()
        if positions:
            print(f"\nÅbne positioner ({len(positions)}):")
            for p in positions:
                print(f"  {p.symbol}: {p.qty} stk @ ${p.avg_entry_price:.2f} "
                      f"(P&L: ${p.unrealized_pl:.2f})")
        else:
            print("\nIngen åbne positioner")
    else:
        print("Ikke forbundet. Tjek .env filen med dine Alpaca API-nøgler.")
