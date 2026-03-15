"""
InvestAid - Start Trading Bot
Kør: python run_bot.py
"""

import logging
import sys
from pathlib import Path

# Tilføj projektrod til Python path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/bot.log", mode="a", encoding="utf-8"),
    ],
)

if __name__ == "__main__":
    from src.config import get_config
    from src.database import init_db

    cfg = get_config()
    init_db()

    if not cfg.alpaca_api_key or not cfg.alpaca_secret_key:
        print("\n" + "="*60)
        print("FEJL: Alpaca API-nøgler mangler!")
        print("="*60)
        print("1. Kopiér .env.example til .env")
        print("2. Indsæt dine Alpaca paper trading API-nøgler")
        print("   (Opret gratis konto på https://alpaca.markets)")
        print("="*60 + "\n")
        sys.exit(1)

    mode = "PAPER (SIMULERET)" if cfg.is_paper_mode else "⚠️  LIVE (RIGTIGE PENGE)"
    print(f"\n{'='*60}")
    print(f"  InvestAid Trading Bot - {mode}")
    print(f"{'='*60}")
    print(f"  Watchlist: {', '.join(cfg.watchlist.symbols)}")
    print(f"  Max kapital: ${cfg.risk.max_portfolio_value:,.0f}")
    print(f"  Stop-loss: {cfg.risk.stop_loss_pct:.0%} per position")
    print(f"  Check interval: {cfg.strategy.check_interval_minutes} min")
    print(f"{'='*60}\n")

    if not cfg.is_paper_mode:
        print("ADVARSEL: Du er ved at starte LIVE trading med rigtige penge!")
        confirm = input("Skriv 'JA' for at fortsætte: ")
        if confirm.strip() != "JA":
            print("Afbrudt.")
            sys.exit(0)

    from src.scheduler import start_scheduler
    start_scheduler()
