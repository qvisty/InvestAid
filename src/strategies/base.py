"""
InvestAid - Abstrakt Strategy-klasse
Alle strategier arver fra denne base og implementerer generate_signals().
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import pandas as pd


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class Signal:
    symbol: str
    signal: SignalType
    strength: float = 1.0          # 0.0 - 1.0, hvor høj = stærkt signal
    price: Optional[float] = None  # Pris på signal-tidspunkt
    strategy: str = ""
    notes: str = ""


class BaseStrategy(ABC):
    """
    Abstrakt base-klasse for alle handelsstrategier.

    Implementer generate_signals() i subklassen og returner
    et dict med symbol -> Signal for hvert symbol med et signal.
    """

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def generate_signals(
        self,
        data: dict[str, pd.DataFrame],
    ) -> dict[str, Signal]:
        """
        Generer handelssignaler baseret på markedsdata.

        Args:
            data: Dict med symbol -> OHLCV DataFrame

        Returns:
            Dict med symbol -> Signal (kun symboler med BUY/SELL)
        """
        ...

    def get_name(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"
