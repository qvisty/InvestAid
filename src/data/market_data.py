"""
InvestAid - Markedsdata
Henter historiske og realtids kursdata via yfinance.
Bruges primært til backtesting og signal-generering.
"""

import logging
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Alpaca bruger / i krypto-symboler, yfinance bruger -
_CRYPTO_MAP = {
    "BTC/USD": "BTC-USD",
    "ETH/USD": "ETH-USD",
    "SOL/USD": "SOL-USD",
}


def _to_yf_symbol(symbol: str) -> str:
    """Konverter Alpaca-format til yfinance-format"""
    return _CRYPTO_MAP.get(symbol, symbol)


def get_historical_data(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
) -> pd.DataFrame:
    """
    Hent historiske OHLCV data.

    Args:
        symbol: Aktie/ETF/krypto symbol (f.eks. "SPY", "GLD", "BTC/USD")
        period: Tidsperiode ("1mo", "3mo", "6mo", "1y", "2y", "5y")
        interval: Tidsinterval ("1d", "1h", "5m")

    Returns:
        DataFrame med kolonner: Open, High, Low, Close, Volume
    """
    yf_symbol = _to_yf_symbol(symbol)
    try:
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period=period, interval=interval)

        if df.empty:
            logger.warning(f"Ingen data for {symbol} ({yf_symbol})")
            return pd.DataFrame()

        # Standardiser kolonnenavne
        df.index = pd.to_datetime(df.index)
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index.name = "Date"

        logger.debug(f"Hentet {len(df)} rækker for {symbol}")
        return df

    except Exception as e:
        logger.error(f"Fejl ved hentning af data for {symbol}: {e}")
        return pd.DataFrame()


def get_multiple_symbols(
    symbols: list[str],
    period: str = "1y",
    interval: str = "1d",
) -> dict[str, pd.DataFrame]:
    """
    Hent historiske data for flere symboler på én gang.

    Returns:
        Dict med symbol -> DataFrame
    """
    result = {}
    for symbol in symbols:
        df = get_historical_data(symbol, period=period, interval=interval)
        if not df.empty:
            result[symbol] = df
        else:
            logger.warning(f"Springer {symbol} over (ingen data)")
    return result


def get_close_prices(
    symbols: list[str],
    period: str = "1y",
) -> pd.DataFrame:
    """
    Hent kun lukkekurser for flere symboler i en samlet DataFrame.
    Bruges til porteføljeoptimering og backtesting.

    Returns:
        DataFrame med en kolonne per symbol
    """
    close_data = {}
    for symbol in symbols:
        df = get_historical_data(symbol, period=period)
        if not df.empty:
            close_data[symbol] = df["Close"]

    if not close_data:
        return pd.DataFrame()

    combined = pd.DataFrame(close_data)
    combined.dropna(how="all", inplace=True)
    return combined


def get_current_price(symbol: str) -> Optional[float]:
    """
    Hent seneste pris for et symbol.

    Returns:
        Seneste lukkekurs eller None ved fejl
    """
    yf_symbol = _to_yf_symbol(symbol)
    try:
        ticker = yf.Ticker(yf_symbol)
        # fast_info er hurtigere end history()
        price = ticker.fast_info.get("last_price") or ticker.fast_info.get("regularMarketPrice")
        if price:
            return float(price)

        # Fallback: seneste dags data
        df = ticker.history(period="2d", interval="1d")
        if not df.empty:
            return float(df["Close"].iloc[-1])

        return None
    except Exception as e:
        logger.error(f"Fejl ved hentning af pris for {symbol}: {e}")
        return None


def get_current_prices(symbols: list[str]) -> dict[str, float]:
    """Hent seneste priser for flere symboler"""
    prices = {}
    for symbol in symbols:
        price = get_current_price(symbol)
        if price is not None:
            prices[symbol] = price
    return prices


def is_market_open() -> bool:
    """
    Tjek om NYSE er åben lige nu.
    Simpel tidsbaseret check (ingen API-kald nødvendigt).
    """
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("America/New_York"))

    # Lukket i weekenden
    if now.weekday() >= 5:
        return False

    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

    return market_open <= now <= market_close


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("Henter SPY data (1 år)...")
    df = get_historical_data("SPY", period="1y")
    print(df.tail())

    print("\nHenter aktuelle priser...")
    prices = get_current_prices(["SPY", "GLD", "QQQ"])
    for sym, price in prices.items():
        print(f"  {sym}: ${price:.2f}")

    print(f"\nMarked åbent: {is_market_open()}")
