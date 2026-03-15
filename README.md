# InvestAid - Automatisk Investeringsrådgiver

Lokal, automatiseret investeringsbot der handler aktier, ETF'er og krypto baseret på tekniske signaler. Starter sikkert med **paper trading** (simuleret handel med ægte markedsdata).

## Hurtig start

### 1. Installer afhængigheder
```bash
pip install -r requirements.txt
```

### 2. Opret Alpaca konto (gratis)
1. Gå til [alpaca.markets](https://alpaca.markets) og opret en gratis konto
2. Vælg **Paper Trading** → **API Keys** → Generer nøgler
3. Du starter automatisk med **$100.000 simuleret kapital**

### 3. Konfigurer API-nøgler
```bash
cp .env.example .env
# Rediger .env og indsæt dine Alpaca API-nøgler
```

### 4. Start systemet
```bash
# Start alt (bot + dashboard)
python run.py

# Eller separat:
python run_bot.py                        # Kun trading bot
streamlit run run_dashboard.py           # Kun dashboard
```

Dashboard åbner automatisk på **http://localhost:8501**

---

## Funktioner

### Strategier
| Strategi | Beskrivelse |
|----------|-------------|
| **EMA Crossover** | Køb når hurtig EMA krydser over langsom EMA + MACD bekræftelse |
| **RSI Momentum** | Køb ved oversold recovery, sælg ved overbought reversal |
| **HRP Rebalancering** | Månedlig rebalancering til optimale vægte (Hierarchical Risk Parity) |

### Aktivunivers (via Alpaca)
- **Indeksfonde**: SPY, QQQ, VTI
- **Guld**: GLD, IAU
- **Obligationer**: AGG
- **Krypto**: BTC/USD, ETH/USD
- **Enkeltaktier**: Alle US-listede aktier

### Risikostyring
- **Paper trading** som default (ingen rigtige penge)
- **Max kapital**: Konfigurerbar grænse for total eksponering
- **Stop-loss**: Automatisk salg ved X% tab per position
- **Take-profit**: Automatisk salg ved X% gevinst
- **Daglig tabsgrænse**: Stop al handel ved X% dagligt tab

### Dashboard (Streamlit)
- Porteføljeværdi og P&L graf
- Åbne positioner med P&L
- Handelshistorik
- Backtesting med VectorBT
- Konfigurationseditor

---

## Teknologi Stack

| Komponent | Bibliotek | Formål |
|-----------|-----------|--------|
| Broker | [alpaca-py](https://github.com/alpacahq/alpaca-py) | Paper/live trading |
| Markedsdata | [yfinance](https://github.com/ranaroussi/yfinance) | Historisk OHLCV data |
| Teknisk analyse | [pandas-ta](https://github.com/twopirllc/pandas-ta) | 150+ indikatorer |
| Backtesting | [VectorBT](https://github.com/polakowo/vectorbt) | Hurtig strategi-test |
| Porteføljeoptimering | [PyPortfolioOpt](https://github.com/robertmartin8/PyPortfolioOpt) | HRP, Efficient Frontier |
| Dashboard | [Streamlit](https://streamlit.io) | Web UI |
| Database | SQLite + SQLAlchemy | Lokal datalagring |
| Scheduler | APScheduler | Automatisk kørsel |

---

## Projektstruktur

```
InvestAid/
├── src/
│   ├── config.py              # Pydantic indstillingsmodel
│   ├── database.py            # SQLite setup
│   ├── risk_manager.py        # Stop-loss, positionsgrænser
│   ├── portfolio_manager.py   # Koordinerer strategier + handel
│   ├── scheduler.py           # APScheduler
│   ├── data/
│   │   └── market_data.py     # yfinance data
│   ├── broker/
│   │   └── alpaca_client.py   # Alpaca integration
│   └── strategies/
│       ├── trend_following.py # EMA + MACD
│       ├── momentum.py        # RSI
│       └── rebalancing.py     # PyPortfolioOpt HRP
├── dashboard/
│   ├── app.py                 # Streamlit app
│   └── pages/                 # Dashboard sider
├── config/
│   └── settings.yaml          # Brugerindstillinger
├── .env.example               # API-nøgler template
└── requirements.txt
```

---

## Fra paper trading til live trading

1. Kør i **paper trading i mindst 1-2 måneder**
2. Vurder performance i dashboardet (Sharpe ratio, max drawdown)
3. Kør backtests for at bekræfte strategi-robusthed
4. Når du er klar: sæt `LIVE_TRADING=true` i `.env`
5. Botten beder dig bekræfte ved opstart

**Tip**: Start med en lille mængde live kapital (f.eks. $500) og øg gradvist efterhånden som du får tillid til systemet.
