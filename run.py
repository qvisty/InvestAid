"""
InvestAid - Start alt (bot + dashboard)
Kør: python run.py

Starter trading botten og Streamlit dashboardet parallelt.
Botten kører i baggrunden, dashboardet åbner i din browser.
"""

import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent


def start_bot():
    """Kør trading botten i en separat tråd"""
    print("Trading bot starter...")
    subprocess.run(
        [sys.executable, "run_bot.py"],
        cwd=ROOT,
    )


def start_dashboard():
    """Kør Streamlit dashboardet"""
    print("Dashboard starter på http://localhost:8501 ...")
    time.sleep(2)  # Giv botten tid til at initialisere
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "run_dashboard.py",
         "--server.port", "8501",
         "--server.headless", "false"],
        cwd=ROOT,
    )


if __name__ == "__main__":
    print("=" * 60)
    print("  InvestAid - Automatisk Investeringsrådgiver")
    print("=" * 60)
    print()
    print("Starter:")
    print("  - Trading bot (baggrunden)")
    print("  - Dashboard: http://localhost:8501")
    print()
    print("Stop begge med Ctrl+C")
    print("=" * 60)

    # Start bot i baggrundstråd
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()

    # Start dashboard i hovedtråden (blokerer)
    try:
        start_dashboard()
    except KeyboardInterrupt:
        print("\nAfslutter...")
