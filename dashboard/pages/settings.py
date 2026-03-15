"""
InvestAid Dashboard - Indstillinger
Rediger settings.yaml direkte fra dashboardet.
"""

import sys
from pathlib import Path

import yaml
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

CONFIG_FILE = Path(__file__).parent.parent.parent / "config" / "settings.yaml"


def show_settings() -> None:
    st.header("Indstillinger")
    st.caption("Alle ændringer gemmes til config/settings.yaml og træder i kraft ved næste bot-cyklus.")

    # Profil-skift
    from src.risk_profiles import ALL_PROFILES, apply_to_config
    from src.database import get_system_flag

    current_profile = get_system_flag("risk_profile") or "moderate"
    profile_labels = {"conservative": "Forsigtig", "moderate": "Balanceret", "aggressive": "Vækst"}
    label_to_key = {v: k for k, v in profile_labels.items()}

    st.subheader("Investeringsprofil")
    col_p1, col_p2 = st.columns([2, 3])
    with col_p1:
        new_label = st.selectbox(
            "Aktiv profil",
            list(profile_labels.values()),
            index=list(profile_labels.keys()).index(current_profile),
            help="Profilen sætter alle risiko- og strategi-parametre automatisk.",
        )
        new_profile_key = label_to_key[new_label]
        profile = ALL_PROFILES[new_profile_key]

    with col_p2:
        st.markdown(f"**{profile.display_name}** — {profile.tagline}")
        for b in profile.bullets:
            st.markdown(f"• {b}")

    if new_profile_key != current_profile:
        if st.button(f"Skift til {profile.display_name}-profil", type="primary"):
            apply_to_config(new_profile_key)
            st.success(f"Profil opdateret til {profile.display_name}. Genstart botten for at anvende.")
            st.cache_data.clear()
            st.rerun()

    st.divider()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as e:
        st.error(f"Kan ikke læse settings.yaml: {e}")
        return

    risk = cfg.get("risk", {})
    strategy = cfg.get("strategy", {})
    watchlist = cfg.get("watchlist", {})
    scheduler_cfg = cfg.get("scheduler", {})

    # Risiko
    st.subheader("Risikostyring")
    col1, col2 = st.columns(2)
    with col1:
        paper = st.toggle(
            "Paper Trading (simuleret)",
            value=risk.get("paper_trading", True),
            help="ALTID start her. Sluk kun når du er klar til rigtige penge.",
        )
        max_value = st.number_input(
            "Max kapital (USD)",
            min_value=100.0,
            max_value=1_000_000.0,
            value=float(risk.get("max_portfolio_value", 5000)),
            step=500.0,
            help="Det maksimale beløb der må investeres ad gangen",
        )
    with col2:
        stop_loss = st.slider(
            "Stop-loss (%)",
            min_value=1, max_value=20,
            value=int(risk.get("stop_loss_pct", 0.05) * 100),
            help="Sælg automatisk hvis en position falder med X%",
        )
        take_profit = st.slider(
            "Take-profit (%)",
            min_value=5, max_value=100,
            value=int(risk.get("take_profit_pct", 0.15) * 100),
            help="Sælg automatisk hvis en position stiger med X%",
        )
        max_pos_pct = st.slider(
            "Max position størrelse (%)",
            min_value=1, max_value=50,
            value=int(risk.get("max_position_pct", 0.05) * 100),
            help="Max andel af portefølje i én aktie",
        )
        max_daily_loss = st.slider(
            "Max dagligt tab (%)",
            min_value=1, max_value=20,
            value=int(risk.get("max_daily_loss_pct", 0.02) * 100),
            help="Stop handel for dagen hvis porteføljen falder med X%",
        )

    st.divider()

    # Strategi
    st.subheader("Strategier")
    col3, col4 = st.columns(2)
    with col3:
        trend_on = st.toggle("EMA Trend Following", value=strategy.get("trend_following_enabled", True))
        momentum_on = st.toggle("RSI Momentum", value=strategy.get("momentum_enabled", True))
        rebalancing_on = st.toggle("Portfolio Rebalancering", value=strategy.get("rebalancing_enabled", True))
        interval = st.number_input(
            "Check interval (minutter)",
            min_value=1, max_value=60,
            value=int(strategy.get("check_interval_minutes", 15)),
        )
    with col4:
        fast_ema = st.number_input("Hurtig EMA periode", min_value=2, max_value=50,
                                    value=int(strategy.get("ema_fast_period", 12)))
        slow_ema = st.number_input("Langsom EMA periode", min_value=5, max_value=200,
                                    value=int(strategy.get("ema_slow_period", 26)))
        rsi_oversold = st.number_input("RSI Oversold grænse", min_value=10, max_value=45,
                                        value=int(strategy.get("rsi_oversold", 30)))
        rsi_overbought = st.number_input("RSI Overbought grænse", min_value=55, max_value=90,
                                          value=int(strategy.get("rsi_overbought", 70)))
        rebalance_days = st.number_input("Rebalancering (dage)", min_value=1, max_value=365,
                                          value=int(strategy.get("rebalancing_interval_days", 30)))

    st.divider()

    # Watchlist
    st.subheader("Watchlist")
    current_symbols = watchlist.get("symbols", [])
    symbols_text = st.text_area(
        "Symboler (ét per linje)",
        value="\n".join(current_symbols),
        height=150,
        help="US aktier (AAPL), ETF'er (SPY, GLD), krypto (BTC/USD)",
    )

    st.divider()

    # Gem
    if st.button("Gem indstillinger", type="primary"):
        new_symbols = [s.strip().upper() for s in symbols_text.strip().split("\n") if s.strip()]

        new_cfg = {
            "risk": {
                "paper_trading": paper,
                "max_portfolio_value": float(max_value),
                "max_position_pct": max_pos_pct / 100,
                "stop_loss_pct": stop_loss / 100,
                "take_profit_pct": take_profit / 100,
                "max_daily_loss_pct": max_daily_loss / 100,
            },
            "strategy": {
                "trend_following_enabled": trend_on,
                "momentum_enabled": momentum_on,
                "rebalancing_enabled": rebalancing_on,
                "check_interval_minutes": int(interval),
                "ema_fast_period": int(fast_ema),
                "ema_slow_period": int(slow_ema),
                "rsi_period": 14,
                "rsi_oversold": float(rsi_oversold),
                "rsi_overbought": float(rsi_overbought),
                "rebalancing_interval_days": int(rebalance_days),
            },
            "watchlist": {"symbols": new_symbols},
            "scheduler": scheduler_cfg,
        }

        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                yaml.dump(new_cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

            from src.config import reload_config
            reload_config()

            st.success("Indstillinger gemt! Genstart botten for at anvende ændringerne.")
        except Exception as e:
            st.error(f"Fejl ved gemning: {e}")
