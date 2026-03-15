"""
InvestAid - Database (SQLite + SQLAlchemy)
Gemmer handler, portfolio snapshots og signaler lokalt.
"""

from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "data" / "investaid.db"


class Base(DeclarativeBase):
    pass


class Trade(Base):
    """Alle udførte handler"""
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    symbol = Column(String(20), nullable=False)
    side = Column(String(4), nullable=False)          # "buy" eller "sell"
    qty = Column(Float, nullable=False)
    price = Column(Float, nullable=True)               # Fyldt pris (None hvis pending)
    order_id = Column(String(100), nullable=True)      # Alpaca order ID
    strategy = Column(String(50), nullable=True)       # Hvilken strategi genererede ordren
    paper = Column(Boolean, default=True)              # Paper eller live handel
    status = Column(String(20), default="submitted")   # submitted, filled, cancelled


class PortfolioSnapshot(Base):
    """Daglig snapshot af porteføljeværdi"""
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    total_value = Column(Float, nullable=False)        # Samlet porteføljeværdi (USD)
    cash = Column(Float, nullable=False)               # Likvide midler
    invested = Column(Float, nullable=False)           # Investeret beløb
    daily_pnl = Column(Float, default=0.0)             # Dagens P&L (USD)
    daily_pnl_pct = Column(Float, default=0.0)         # Dagens P&L (%)
    paper = Column(Boolean, default=True)


class Signal(Base):
    """Genererede handelssignaler (til analyse og debugging)"""
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    symbol = Column(String(20), nullable=False)
    strategy = Column(String(50), nullable=False)
    signal = Column(String(10), nullable=False)        # "BUY", "SELL", "HOLD"
    strength = Column(Float, default=1.0)              # Signalstyrke 0-1
    price = Column(Float, nullable=True)               # Pris på signal-tidspunkt
    notes = Column(String(500), nullable=True)


# Database engine og session factory
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    """Opret database og tabeller hvis de ikke eksisterer"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    """Hent en database session"""
    return SessionLocal()


def save_trade(
    symbol: str,
    side: str,
    qty: float,
    price: float | None = None,
    order_id: str | None = None,
    strategy: str | None = None,
    paper: bool = True,
    status: str = "submitted",
) -> Trade:
    """Gem en handel i databasen"""
    with get_session() as session:
        trade = Trade(
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            order_id=order_id,
            strategy=strategy,
            paper=paper,
            status=status,
        )
        session.add(trade)
        session.commit()
        session.refresh(trade)
        return trade


def save_portfolio_snapshot(
    total_value: float,
    cash: float,
    invested: float,
    daily_pnl: float = 0.0,
    daily_pnl_pct: float = 0.0,
    paper: bool = True,
) -> PortfolioSnapshot:
    """Gem et portfolio snapshot"""
    with get_session() as session:
        snap = PortfolioSnapshot(
            total_value=total_value,
            cash=cash,
            invested=invested,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            paper=paper,
        )
        session.add(snap)
        session.commit()
        session.refresh(snap)
        return snap


def save_signal(
    symbol: str,
    strategy: str,
    signal: str,
    strength: float = 1.0,
    price: float | None = None,
    notes: str | None = None,
) -> Signal:
    """Gem et handelssignal"""
    with get_session() as session:
        sig = Signal(
            symbol=symbol,
            strategy=strategy,
            signal=signal,
            strength=strength,
            price=price,
            notes=notes,
        )
        session.add(sig)
        session.commit()
        session.refresh(sig)
        return sig


if __name__ == "__main__":
    init_db()
    print(f"Database oprettet: {DB_PATH}")
