"""
InvestAid - Setup Wizard (Første-gangs onboarding)
Vises kun ved allerførste opstart. Stiller 4 simple spørgsmål
og konfigurerer automatisk den bedst egnede investeringsprofil.

Ingen finansiel viden krævet.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def show_setup_wizard() -> None:
    from src.risk_profiles import ALL_PROFILES, apply_to_config, score_to_profile

    st.title("Velkommen til InvestAid")
    st.markdown(
        "Lad os konfigurere systemet til dig. Besvar 4 korte spørgsmål — "
        "ingen finansiel viden krævet. Det tager under 1 minut."
    )
    st.divider()

    # ---------------------------------------------------------- #
    #  Spørgsmål 1: Investeringshorisont                          #
    # ---------------------------------------------------------- #
    st.subheader("1. Hvornår har du (måske) brug for pengene igen?")
    horizon = st.radio(
        "",
        [
            "Inden for 1-3 år — jeg har pengene til noget specifikt",
            "Om 3-10 år — mellemlang sigt",
            "Om 10+ år — det er til pension eller lignende",
        ],
        label_visibility="collapsed",
        key="wizard_horizon",
    )
    horizon_score = ["Inden for 1-3 år", "Om 3-10 år", "Om 10+ år"].index(
        next(o for o in ["Inden for 1-3 år", "Om 3-10 år", "Om 10+ år"] if o in horizon)
    )

    st.divider()

    # ---------------------------------------------------------- #
    #  Spørgsmål 2: Reaktion på tab                              #
    # ---------------------------------------------------------- #
    st.subheader("2. Forestil dig at din portefølje falder 20% på én måned.")
    st.caption("Hvad ville du gøre?")
    reaction = st.radio(
        "",
        [
            "Sælge — jeg vil ikke tabe mere",
            "Ingenting — jeg venter på at det vender",
            "Købe mere — det er en god mulighed",
        ],
        label_visibility="collapsed",
        key="wizard_reaction",
    )
    reaction_score = 0 if "Sælge" in reaction else (1 if "Ingenting" in reaction else 2)

    st.divider()

    # ---------------------------------------------------------- #
    #  Spørgsmål 3: Månedlig kapacitet                           #
    # ---------------------------------------------------------- #
    st.subheader("3. Hvad er din månedlige opsparing du kan afsætte?")
    savings = st.radio(
        "",
        [
            "Under $500",
            "$500 – $2.000",
            "Over $2.000",
        ],
        label_visibility="collapsed",
        key="wizard_savings",
    )
    savings_score = ["Under $500", "$500 – $2.000", "Over $2.000"].index(savings)

    st.divider()

    # ---------------------------------------------------------- #
    #  Spørgsmål 4: Start-kapital                                #
    # ---------------------------------------------------------- #
    st.subheader("4. Hvor meget vil du starte med?")
    st.caption(
        "Dette er det beløb systemet må investere. Du kan altid ændre det senere. "
        "Det anbefales at starte i paper trading (simuleret) uanset beløb."
    )
    start_capital = st.number_input(
        "Start-kapital (USD)",
        min_value=100,
        max_value=1_000_000,
        value=2000,
        step=100,
        key="wizard_capital",
    )

    st.divider()

    # ---------------------------------------------------------- #
    #  Beregn anbefalet profil                                    #
    # ---------------------------------------------------------- #
    profile_name = score_to_profile(horizon_score, reaction_score, savings_score)
    profile = ALL_PROFILES[profile_name]

    profile_colors = {
        "conservative": "#2196F3",
        "moderate": "#00C851",
        "aggressive": "#FF8800",
    }
    color = profile_colors[profile_name]

    st.markdown(f"""
    <div style="border-left: 4px solid {color}; padding: 12px 20px; background: {color}11; border-radius: 4px">
        <h3 style="color:{color}; margin:0">Anbefalet profil: {profile.display_name}</h3>
        <p style="margin: 8px 0 0 0; color: #555">{profile.tagline}</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"\n{profile.description}\n")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Hvad det betyder:**")
        for bullet in profile.bullets:
            st.markdown(f"• {bullet}")

    with col2:
        st.markdown("**Tekniske indstillinger (sat automatisk):**")
        st.markdown(f"• Stop-loss: {profile.stop_loss_pct:.0%} per position")
        st.markdown(f"• Take-profit: {profile.take_profit_pct:.0%}")
        st.markdown(f"• Max position: {profile.max_position_pct:.0%} af portefølje")
        st.markdown(f"• Rebalancering: hvert {profile.rebalancing_interval_days}. dag")
        st.markdown(f"• ETF'er: {', '.join(profile.symbols[:4])}{'...' if len(profile.symbols) > 4 else ''}")

    st.divider()

    # Mulighed for at vælge en anden profil
    with st.expander("Vil du vælge en anden profil manuelt?"):
        manual = st.radio(
            "Vælg profil:",
            ["Forsigtig", "Balanceret", "Vækst"],
            index=["Forsigtig", "Balanceret", "Vækst"].index(
                {"conservative": "Forsigtig", "moderate": "Balanceret", "aggressive": "Vækst"}[profile_name]
            ),
            key="wizard_manual",
            horizontal=True,
        )
        profile_name_override = {"Forsigtig": "conservative", "Balanceret": "moderate", "Vækst": "aggressive"}[manual]
        if profile_name_override != profile_name:
            profile_name = profile_name_override
            profile = ALL_PROFILES[profile_name]
            st.info(f"Du har valgt profilen: **{profile.display_name}** — {profile.tagline}")

    st.divider()

    # Start-knap
    col_btn, col_note = st.columns([1, 3])
    with col_btn:
        if st.button("Start InvestAid", type="primary", use_container_width=True):
            with st.spinner("Konfigurerer systemet..."):
                try:
                    from src.database import init_db
                    init_db()
                    apply_to_config(profile_name, start_capital=float(start_capital))
                    st.success(
                        f"Systemet er konfigureret med profilen **{profile.display_name}**. "
                        f"Konfiguration gemt!"
                    )
                    st.balloons()
                    st.info(
                        "Start botten i en terminal:\n\n"
                        "```\npython run_bot.py\n```\n\n"
                        "Derefter opdateres dashboardet automatisk."
                    )
                    # Nulstil cache og genindlæs
                    st.cache_data.clear()
                    import time
                    time.sleep(2)
                    st.rerun()
                except Exception as e:
                    st.error(f"Fejl: {e}")

    with col_note:
        st.caption(
            "Systemet starter i **paper trading** (simuleret handel med ægte markedsdata). "
            "Ingen rigtige penge bruges. Du kan skifte til live trading under Indstillinger "
            "når du har tillid til systemet."
        )
