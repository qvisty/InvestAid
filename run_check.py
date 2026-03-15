"""
InvestAid Pre-flight Check
Verificér at alle komponenter er klar inden botten startes første gang.

Kør: python run_check.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

PASS = "✅"
FAIL = "❌"
INFO = "⚪"
WARN = "⚠️ "

results = []
config_lines = []
all_ok = True


def ok(label: str, detail: str = "") -> None:
    line = f"{PASS}  {label}"
    if detail:
        line += f"\n    {detail}"
    results.append(line)


def fail(label: str, hint: str = "") -> None:
    global all_ok
    all_ok = False
    line = f"{FAIL}  {label}"
    if hint:
        line += f"\n    → {hint}"
    results.append(line)


def info(label: str, detail: str = "") -> None:
    line = f"{INFO}  {label}"
    if detail:
        line += f"\n    {detail}"
    results.append(line)


def warn(label: str, detail: str = "") -> None:
    line = f"{WARN} {label}"
    if detail:
        line += f"\n    {detail}"
    results.append(line)


# ------------------------------------------------------------------ #
#  1. .env fil                                                         #
# ------------------------------------------------------------------ #
env_path = Path(".env")
if env_path.exists():
    content = env_path.read_text()
    missing = []
    if "ALPACA_API_KEY" not in content or "your_" in content.split("ALPACA_API_KEY")[-1].split("\n")[0]:
        missing.append("ALPACA_API_KEY")
    if "ALPACA_SECRET_KEY" not in content or "your_" in content.split("ALPACA_SECRET_KEY")[-1].split("\n")[0]:
        missing.append("ALPACA_SECRET_KEY")
    if missing:
        fail(".env fundet, men nøgler er ikke udfyldt",
             f"Indsæt rigtige værdier for: {', '.join(missing)}")
    else:
        ok(".env fil fundet")
else:
    fail(".env fil mangler",
         "Kopiér .env.example til .env og indsæt dine Alpaca API-nøgler")

# ------------------------------------------------------------------ #
#  2. Konfiguration                                                    #
# ------------------------------------------------------------------ #
cfg = None
try:
    from src.config import get_config
    cfg = get_config()
    config_lines.append(f"Watchlist:    {len(cfg.watchlist.symbols)} symboler "
                        f"({', '.join(cfg.watchlist.symbols[:5])}"
                        + ("..." if len(cfg.watchlist.symbols) > 5 else "") + ")")
    config_lines.append(f"Max kapital:  ${cfg.risk.max_portfolio_value:,.0f}")
    config_lines.append(f"Stop-loss:    {cfg.risk.stop_loss_pct:.0%}  |  "
                        f"Take-profit: {cfg.risk.take_profit_pct:.0%}")
    config_lines.append(f"Interval:     {cfg.strategy.check_interval_minutes} min")
except Exception as e:
    fail(f"Konfigurationsfejl: {e}", "Tjek config/settings.yaml og .env")

# ------------------------------------------------------------------ #
#  3. Alpaca forbindelse                                               #
# ------------------------------------------------------------------ #
account = None
if cfg:
    try:
        from src.broker.alpaca_client import create_client_from_config
        client = create_client_from_config()
        account = client.get_account()
        if account:
            mode_label = "PAPER mode" if cfg.is_paper_mode else "LIVE mode"
            ok(f"Alpaca forbundet ({mode_label})",
               f"Konto: ${account.portfolio_value:,.2f}  |  "
               f"Købekraft: ${account.buying_power:,.2f}")
            if not cfg.is_paper_mode:
                warn("Du er i LIVE mode — rigtige penge er på spil",
                     "Skift til paper trading: sæt ALPACA_PAPER=true i .env")
        else:
            fail("Alpaca svarede, men returnerede ingen kontostatus",
                 "Tjek at API-nøglerne tilhører en paper trading konto")
    except Exception as e:
        err = str(e)
        if "forbidden" in err.lower() or "unauthorized" in err.lower() or "403" in err:
            fail("Alpaca: ugyldige API-nøgler",
                 "Tjek ALPACA_API_KEY og ALPACA_SECRET_KEY i .env")
        elif "connection" in err.lower() or "timeout" in err.lower():
            fail("Alpaca: ingen forbindelse",
                 "Tjek din internetforbindelse og prøv igen")
        else:
            fail(f"Alpaca fejl: {err[:100]}")

# ------------------------------------------------------------------ #
#  4. Markedsdata                                                      #
# ------------------------------------------------------------------ #
market_data = None
try:
    from src.data.market_data import get_multiple_symbols
    market_data = get_multiple_symbols(["SPY", "QQQ"], period="1mo", interval="1d")
    if market_data:
        sample = next(iter(market_data.values()))
        ok("Markedsdata (yfinance)",
           f"SPY/QQQ: {len(sample)} dages data hentet")
    else:
        fail("Markedsdata: ingen data returneret",
             "Tjek din internetforbindelse — yfinance kræver adgang til Yahoo Finance")
except Exception as e:
    fail(f"Markedsdata fejl: {str(e)[:100]}",
         "Tjek internetforbindelsen og at yfinance er installeret")

# ------------------------------------------------------------------ #
#  5. Strategi-filtre (live regime-check)                             #
# ------------------------------------------------------------------ #
if market_data:
    try:
        from src.strategies.filters import adx_filter, regime_filter, volume_filter

        filter_parts = []
        for symbol in list(market_data.keys())[:3]:
            df = market_data[symbol]
            close = df["Close"]
            volume = df.get("Volume") if hasattr(df, "get") else (df["Volume"] if "Volume" in df.columns else None)
            r = regime_filter(close)
            a = adx_filter(df)
            v = volume_filter(volume) if volume is not None else None
            regime_s = "Bull" if r else "Bear"
            adx_s = "Trend" if a else "Sideværts"
            vol_s = ("Vol-ok" if v else "Lav-vol") if v is not None else "—"
            filter_parts.append(f"{symbol}: {regime_s} | {adx_s} | {vol_s}")

        ok("Strategi-filtre aktive", "  ".join(filter_parts))
    except Exception as e:
        fail(f"Filter-fejl: {str(e)[:100]}")

# ------------------------------------------------------------------ #
#  6. Database                                                         #
# ------------------------------------------------------------------ #
try:
    from src.database import DB_PATH, init_db
    init_db()
    ok("Database klar", str(DB_PATH))
except Exception as e:
    fail(f"Database fejl: {str(e)[:100]}",
         "Tjek at data/-mappen eksisterer og er skrivbar")

# ------------------------------------------------------------------ #
#  7. E-mail                                                           #
# ------------------------------------------------------------------ #
if cfg:
    try:
        from src.notifications.email_notifier import create_notifier_from_config
        notifier = create_notifier_from_config()
        if notifier.is_enabled:
            ok("E-mail notifikationer aktive",
               f"Sender til: {getattr(cfg.notifications, 'email_to', '(se .env)')}")
        else:
            info("E-mail: ikke konfigureret (valgfrit)",
                 "Tilføj EMAIL_TO og SMTP-indstillinger i .env for at aktivere")
    except Exception:
        info("E-mail: ikke konfigureret (valgfrit)")

# ------------------------------------------------------------------ #
#  Print rapport                                                       #
# ------------------------------------------------------------------ #
width = 54
print()
print("InvestAid Pre-flight Check")
print("═" * width)
for line in results:
    print(line)

if config_lines:
    print("─" * width)
    print("Konfiguration:")
    for line in config_lines:
        print(f"    {line}")

print("═" * width)

if all_ok:
    print(f"{PASS}  Alt klar!  Kør: python run_bot.py")
else:
    print(f"{FAIL}  Ret fejlene ovenfor og kør run_check.py igen")

print()
sys.exit(0 if all_ok else 1)
