"""
InvestAid - Risikoprofiler
Tre vidensbaserede investeringsprofiler baseret på akademisk og industri-forskning.

Kildegrundlag:
- Vanguard Investment Methodology (2023)
- Fama-French trefaktormodel (momentum, value, quality)
- CFA Institute: Risk Management Guidelines
- BlackRock Portfolio Construction Principles
- Morningstar Model Portfolio Research

Brugeren svarer på 4 spørgsmål → profil vælges automatisk.
Profilen sætter ALLE parametre — brugeren behøver ikke forstå dem.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

ProfileName = Literal["conservative", "moderate", "aggressive"]

CONFIG_FILE = Path(__file__).parent.parent / "config" / "settings.yaml"


@dataclass
class RiskProfile:
    name: ProfileName
    display_name: str
    tagline: str
    description: str

    # Watchlist — lavprisede, likvide ETF'er anbefalet af Vanguard/Fidelity
    symbols: list[str]

    # Risikoparametre
    max_portfolio_value: float
    max_position_pct: float       # Max andel i én position
    stop_loss_pct: float          # Sælg ved X% tab
    take_profit_pct: float        # Sælg ved X% gevinst
    max_daily_loss_pct: float     # Stop handel hvis portefølje falder X% på én dag
    min_order_notional: float     # Minimum ordrestørrelse (USD)

    # Strategiparametre
    ema_fast_period: int          # Hurtig EMA til trend-signal
    ema_slow_period: int          # Langsom EMA (golden cross = 50/200 er industri-standard)
    rsi_period: int
    rsi_oversold: float
    rsi_overbought: float
    rebalancing_interval_days: int

    # Strategier aktiveret
    trend_following_enabled: bool = True
    momentum_enabled: bool = True
    rebalancing_enabled: bool = True

    # Forklaring til brugeren
    bullets: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ #
#  Profil 1: CONSERVATIVE                                             #
#  Målgruppe: kort horisont (1-3 år), lav risikotolerance            #
#  Model: Vanguard LifeStrategy Conservative (80% bonds / 20% equity)#
# ------------------------------------------------------------------ #
CONSERVATIVE = RiskProfile(
    name="conservative",
    display_name="Forsigtig",
    tagline="Kapitalbevarelse frem for vækst",
    description=(
        "Fokus på at bevare din kapital og undgå store tab. "
        "Investerer primært i brede indeksfonde og obligationer. "
        "Passer til dig der har brug for pengene inden for 1-3 år, "
        "eller som sover dårligt hvis investeringen falder."
    ),
    symbols=[
        "VTI",    # Vanguard Total Stock Market (0.03% ÅOP — industris laveste)
        "BND",    # Vanguard Total Bond Market (0.03% ÅOP)
        "AGG",    # iShares Core US Aggregate Bond (obligationer, stabilitet)
        "GLD",    # SPDR Gold ETF (inflation-hedge, krisebeskyttelse)
        "VXUS",   # Vanguard Total International Stock (global spredning)
        "SCHD",   # Schwab US Dividend Equity (udbytte-fokus, lavere volatilitet)
    ],
    max_portfolio_value=5000.0,
    max_position_pct=0.10,        # Max 10% i én position (færre, større positioner)
    stop_loss_pct=0.08,           # 8% stop-loss — løsere end standard for at undgå whipsawing
    take_profit_pct=0.20,         # 20% take-profit
    max_daily_loss_pct=0.03,      # Stop handel ved 3% dagligt tab
    min_order_notional=100.0,     # Minimum $100 per ordre (gebyrer ubetydelige)
    ema_fast_period=50,           # Golden cross (50/200) — industri-standard langsigtet trend
    ema_slow_period=200,
    rsi_period=14,
    rsi_oversold=25.0,            # Bredere bånd = færre, men mere overbevisende signaler
    rsi_overbought=75.0,
    rebalancing_interval_days=90, # Kvartalsvis rebalancering (minimér transaktionsomkostninger)
    trend_following_enabled=True,
    momentum_enabled=False,       # Momentum deaktiveret — for volatil til konservativ profil
    rebalancing_enabled=True,
    bullets=[
        "Primært obligationer og brede indeksfonde",
        "Stop-loss ved 8% tab per position",
        "Rebalancering hvert kvartal",
        "Ingen krypto eller enkeltaktier",
        "Lav handelsfrekvens = lave gebyrer",
    ],
)

# ------------------------------------------------------------------ #
#  Profil 2: MODERATE (DEFAULT)                                       #
#  Målgruppe: mellemlang horisont (3-10 år), moderat risikotolerance #
#  Model: Vanguard LifeStrategy Moderate (60% equity / 40% bonds)    #
# ------------------------------------------------------------------ #
MODERATE = RiskProfile(
    name="moderate",
    display_name="Balanceret",
    tagline="Langsigtet vækst med kontrolleret risiko",
    description=(
        "Balancerer vækst og stabilitet. Investerer i globale aktier, "
        "obligationer og guld med moderate risikobegrænsninger. "
        "Passer til dig der har en investeringshorisont på 3-10 år "
        "og kan tåle kortsigtede udsving på op til 20%."
    ),
    symbols=[
        "SPY",      # S&P 500 (USA's 500 største virksomheder)
        "QQQ",      # Nasdaq 100 (teknologi og vækst)
        "VTI",      # Vanguard Total Stock Market (bredeste US ETF)
        "VXUS",     # Vanguard International (global spredning)
        "GLD",      # SPDR Gold (krisebeskyttelse)
        "AGG",      # US Aggregate Bond (obligationer)
        "SCHD",     # Schwab Dividend Equity (kvalitets-aktier med udbytte)
        "VIG",      # Vanguard Dividend Appreciation (stabile udbyttevæksere)
        "BTC/USD",  # Bitcoin (lille allokering for asymmetrisk upside)
        "ETH/USD",  # Ethereum (blockchain-eksponering)
    ],
    max_portfolio_value=5000.0,
    max_position_pct=0.07,        # Max 7% per position
    stop_loss_pct=0.10,           # 10% stop-loss
    take_profit_pct=0.25,         # 25% take-profit
    max_daily_loss_pct=0.02,      # Stop handel ved 2% dagligt tab
    min_order_notional=50.0,
    ema_fast_period=20,           # Medium-term trend (20/50 balancerer signal/støj)
    ema_slow_period=50,
    rsi_period=14,
    rsi_oversold=30.0,
    rsi_overbought=70.0,
    rebalancing_interval_days=60, # Ca. 2-månedlig rebalancering
    trend_following_enabled=True,
    momentum_enabled=True,
    rebalancing_enabled=True,
    bullets=[
        "Global aktie-eksponering via brede indeksfonde",
        "Obligationer og guld som stabilisatorer",
        "Stop-loss ved 10% tab per position",
        "Lille krypto-allokering (under 15% af portefølje)",
        "Rebalancering hver 2. måned",
    ],
)

# ------------------------------------------------------------------ #
#  Profil 3: AGGRESSIVE                                               #
#  Målgruppe: lang horisont (10+ år), høj risikotolerance            #
#  Model: Momentum/growth-orienteret med bred diversificering         #
# ------------------------------------------------------------------ #
AGGRESSIVE = RiskProfile(
    name="aggressive",
    display_name="Vækst",
    tagline="Maksimal langsigtet vækst",
    description=(
        "Fokus på høj langsigtet afkast. Investerer i vækst-ETF'er, "
        "teknologi og krypto med bredere stop-loss. "
        "Passer til dig der har 10+ år og kan tåle at se porteføljen "
        "falde 30-40% midlertidigt uden at sælge i panik."
    ),
    symbols=[
        "SPY",      # S&P 500
        "QQQ",      # Nasdaq 100 (teknologi-tung)
        "VTI",      # Total Market
        "VXUS",     # International
        "GLD",      # Guld
        "IAU",      # iShares Gold (alternativ til GLD)
        "BTC/USD",  # Bitcoin
        "ETH/USD",  # Ethereum
        "ARKK",     # ARK Innovation ETF (disruptiv teknologi)
        "SPLG",     # SPDR Portfolio S&P 500 (lavpris-alternativ til SPY)
        "VGT",      # Vanguard Information Technology ETF
        "SOXX",     # iShares Semiconductor ETF
    ],
    max_portfolio_value=5000.0,
    max_position_pct=0.05,        # Max 5% per position (bredere spredning)
    stop_loss_pct=0.15,           # 15% stop-loss (bredere for volatile aktiver)
    take_profit_pct=0.40,         # 40% take-profit
    max_daily_loss_pct=0.03,
    min_order_notional=50.0,
    ema_fast_period=12,           # Hurtige signaler (12/26 = standard MACD-perioder)
    ema_slow_period=26,
    rsi_period=14,
    rsi_oversold=30.0,
    rsi_overbought=70.0,
    rebalancing_interval_days=30, # Månedlig rebalancering
    trend_following_enabled=True,
    momentum_enabled=True,
    rebalancing_enabled=True,
    bullets=[
        "Vækst-fokuserede ETF'er og teknologi",
        "Krypto-allokering op til 20% af portefølje",
        "Bredere stop-loss (15%) for at undgå at sælge i kortsigtede dyk",
        "Hurtige handelssignaler — reagerer hurtigt på trends",
        "Månedlig rebalancering",
    ],
)

ALL_PROFILES: dict[ProfileName, RiskProfile] = {
    "conservative": CONSERVATIVE,
    "moderate": MODERATE,
    "aggressive": AGGRESSIVE,
}


def get_profile(name: ProfileName) -> RiskProfile:
    return ALL_PROFILES[name]


def apply_to_config(profile_name: ProfileName, start_capital: float | None = None) -> None:
    """
    Skriv profil-indstillinger til config/settings.yaml.
    Kaldes når brugeren gennemfører setup-wizarden eller skifter profil.
    """
    profile = get_profile(profile_name)

    # Læs eksisterende config for at bevare ikke-profil-felter
    existing: dict = {}
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}

    max_value = start_capital if start_capital else profile.max_portfolio_value

    new_cfg = {
        "risk_profile": profile_name,
        "risk": {
            "paper_trading": existing.get("risk", {}).get("paper_trading", True),
            "max_portfolio_value": max_value,
            "max_position_pct": profile.max_position_pct,
            "stop_loss_pct": profile.stop_loss_pct,
            "take_profit_pct": profile.take_profit_pct,
            "max_daily_loss_pct": profile.max_daily_loss_pct,
            "min_order_notional": profile.min_order_notional,
        },
        "strategy": {
            "trend_following_enabled": profile.trend_following_enabled,
            "momentum_enabled": profile.momentum_enabled,
            "rebalancing_enabled": profile.rebalancing_enabled,
            "check_interval_minutes": existing.get("strategy", {}).get("check_interval_minutes", 15),
            "ema_fast_period": profile.ema_fast_period,
            "ema_slow_period": profile.ema_slow_period,
            "rsi_period": profile.rsi_period,
            "rsi_oversold": profile.rsi_oversold,
            "rsi_overbought": profile.rsi_overbought,
            "rebalancing_interval_days": profile.rebalancing_interval_days,
        },
        "watchlist": {
            "symbols": profile.symbols,
        },
        "scheduler": existing.get("scheduler", {
            "market_open": "09:30",
            "market_close": "16:00",
            "timezone": "America/New_York",
            "run_on_weekends": False,
        }),
    }

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(new_cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # Gem profil-navn i database-flag
    try:
        from src.database import set_system_flag
        set_system_flag("risk_profile", profile_name, notes=f"Start kapital: ${max_value:,.0f}")
    except Exception:
        pass

    # Nulstil config-singleton så nye værdier indlæses
    try:
        from src.config import reload_config
        reload_config()
    except Exception:
        pass


def score_to_profile(
    horizon_score: int,    # 0=kort, 1=mellem, 2=langt
    reaction_score: int,   # 0=sælge, 1=holde, 2=købe mere
    savings_score: int,    # 0=lav, 1=middel, 2=høj
) -> ProfileName:
    """
    Map brugerens svar til en profil via simpel scoring.
    Total 0-2 = conservative, 3-4 = moderate, 5-6 = aggressive.
    """
    total = horizon_score + reaction_score + savings_score
    if total <= 2:
        return "conservative"
    elif total <= 4:
        return "moderate"
    else:
        return "aggressive"
