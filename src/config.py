"""
InvestAid - Konfigurationsmodel
Læser settings.yaml + .env og validerer alle indstillinger.
"""

import os
from pathlib import Path
from typing import List

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
CONFIG_FILE = BASE_DIR / "config" / "settings.yaml"


class RiskConfig(BaseModel):
    paper_trading: bool = True
    max_portfolio_value: float = Field(5000.0, gt=0)
    max_position_pct: float = Field(0.05, gt=0, le=1.0)
    stop_loss_pct: float = Field(0.05, gt=0, le=1.0)
    take_profit_pct: float = Field(0.15, gt=0, le=10.0)
    max_daily_loss_pct: float = Field(0.02, gt=0, le=1.0)


class StrategyConfig(BaseModel):
    trend_following_enabled: bool = True
    momentum_enabled: bool = True
    rebalancing_enabled: bool = True
    check_interval_minutes: int = Field(15, ge=1)
    ema_fast_period: int = Field(12, ge=2)
    ema_slow_period: int = Field(26, ge=5)
    rsi_period: int = Field(14, ge=2)
    rsi_oversold: float = Field(30.0, ge=10, le=50)
    rsi_overbought: float = Field(70.0, ge=50, le=90)
    rebalancing_interval_days: int = Field(30, ge=1)


class WatchlistConfig(BaseModel):
    symbols: List[str] = ["SPY", "QQQ", "GLD", "BTC/USD"]

    @field_validator("symbols")
    @classmethod
    def symbols_not_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("Watchlist skal indeholde mindst ét symbol")
        return [s.upper() for s in v]


class SchedulerConfig(BaseModel):
    market_open: str = "09:30"
    market_close: str = "16:00"
    timezone: str = "America/New_York"
    run_on_weekends: bool = False


class AppConfig(BaseModel):
    risk: RiskConfig = RiskConfig()
    strategy: StrategyConfig = StrategyConfig()
    watchlist: WatchlistConfig = WatchlistConfig()
    scheduler: SchedulerConfig = SchedulerConfig()

    # Alpaca API (fra .env)
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    live_trading: bool = False

    @property
    def alpaca_base_url(self) -> str:
        if self.live_trading and not self.risk.paper_trading:
            return "https://api.alpaca.markets"
        return "https://paper-api.alpaca.markets"

    @property
    def is_paper_mode(self) -> bool:
        return self.risk.paper_trading or not self.live_trading


def load_config() -> AppConfig:
    """Indlæs konfiguration fra settings.yaml og .env"""
    data: dict = {}

    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    config = AppConfig(
        risk=RiskConfig(**data.get("risk", {})),
        strategy=StrategyConfig(**data.get("strategy", {})),
        watchlist=WatchlistConfig(**data.get("watchlist", {})),
        scheduler=SchedulerConfig(**data.get("scheduler", {})),
        alpaca_api_key=os.getenv("ALPACA_API_KEY", ""),
        alpaca_secret_key=os.getenv("ALPACA_SECRET_KEY", ""),
        live_trading=os.getenv("LIVE_TRADING", "false").lower() == "true",
    )

    return config


# Global singleton
_config: AppConfig | None = None


def get_config() -> AppConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> AppConfig:
    global _config
    _config = load_config()
    return _config
