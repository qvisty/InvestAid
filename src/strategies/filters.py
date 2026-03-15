"""
InvestAid - Tekniske filtre til strategierne

Tre veldokumenterede filtre der reducerer falske signaler og forbedrer
risikojusterede afkast:

1. Regime-filter (200-dages MA) — Meb Faber (2007), Gary Antonacci (2014)
   Kun BUY-signaler i bull-regime (pris over langsigtet MA).
   Reducerer max drawdown med 30-40% med minimalt afkaldsafkast.

2. ADX-filter (trendstyrke) — J. Welles Wilder, "New Concepts in Technical Trading Systems"
   Kun trend-following i trendende markeder (ADX > 25).
   Undgår sideværts markeder der genererer whipsaws og falske crossovers.

3. Volumen-filter — William O'Neil, "How to Make Money in Stocks"
   Bekræft breakout-signaler med volumen over 20-dages gennemsnit.
   Signaler med høj volumen er signifikant mere pålidelige.
"""

import logging

import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)


def regime_filter(close: pd.Series, ma_period: int = 200) -> bool:
    """
    Bull/bear-regime filter baseret på langsigtet glidende gennemsnit.

    Returnerer True (bull-regime) hvis seneste kurs er over MA → KØB tilladt.
    Returnerer False (bear-regime) hvis seneste kurs er under MA → KØB blokeret.

    Hvis der ikke er nok data, bruges et kortere MA som fallback.
    Ved utilstrækkelige data returneres True (neutral — undlad at filtrere).
    """
    n = len(close)
    if n < ma_period:
        fallback = min(50, n - 1)
        if fallback < 10:
            return True  # For lidt historik — undlad at filtrere
        period = fallback
    else:
        period = ma_period

    ma = close.rolling(period).mean().iloc[-1]
    if pd.isna(ma):
        return True

    return float(close.iloc[-1]) > float(ma)


def adx_filter(df: pd.DataFrame, threshold: float = 25.0) -> bool:
    """
    ADX trendstyrke-filter (Average Directional Index).

    Returnerer True hvis ADX >= threshold → stærk trend → EMA-signaler er pålidelige.
    Returnerer False hvis ADX < threshold → sideværts marked → undgå trend-following.

    ADX fortolkning:
      < 20: Ingen trend (undgå EMA crossover — for mange falske signaler)
      20-25: Svag trend (borderline)
      > 25: Stærk trend (EMA crossover er pålideligt)
      > 40: Meget stærk trend

    Returnerer True (neutral) ved fejl eller utilstrækkelige data.
    """
    if len(df) < 20:
        return True

    if not all(col in df.columns for col in ["High", "Low", "Close"]):
        return True

    try:
        adx_result = ta.adx(df["High"], df["Low"], df["Close"], length=14)
        if adx_result is None or adx_result.empty:
            return True

        adx_col = [c for c in adx_result.columns if c.startswith("ADX_")]
        if not adx_col:
            return True

        adx_value = adx_result[adx_col[0]].iloc[-1]
        if pd.isna(adx_value):
            return True

        return float(adx_value) >= threshold

    except Exception as e:
        logger.debug(f"ADX-filter fejlede: {e} — returnerer True (neutral)")
        return True


def volume_filter(volume: pd.Series, lookback: int = 20) -> bool:
    """
    Volumen-bekræftelsesfilter.

    Returnerer True hvis seneste bars volumen er over lookback-dages gennemsnit.
    Breakout- og reversal-signaler med høj volumen er markant mere pålidelige.

    Returnerer True (neutral) hvis volume-data ikke er tilgængeligt eller utilstrækkeligt.
    """
    if len(volume) < lookback + 1:
        return True

    avg_volume = volume.iloc[-(lookback + 1):-1].mean()
    current_volume = volume.iloc[-1]

    if pd.isna(avg_volume) or avg_volume == 0:
        return True

    return float(current_volume) >= float(avg_volume)
