"""
InvestAid - Database (SQLite + SQLAlchemy)
Gemmer handler, portfolio snapshots, signaler og live bot-state lokalt.

Bot skriver til databasen — dashboard læser udelukkende fra databasen.
De to processer deler aldrig en direkte forbindelse til Alpaca.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

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
    side = Column(String(4), nullable=False)
    qty = Column(Float, nullable=False)
    price = Column(Float, nullable=True)
    order_id = Column(String(100), nullable=True)
    strategy = Column(String(50), nullable=True)
    paper = Column(Boolean, default=True)
    status = Column(String(20), default="submitted")


class PortfolioSnapshot(Base):
    """Daglig snapshot af porteføljeværdi (til historisk P&L graf)"""
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    total_value = Column(Float, nullable=False)
    cash = Column(Float, nullable=False)
    invested = Column(Float, nullable=False)
    daily_pnl = Column(Float, default=0.0)
    daily_pnl_pct = Column(Float, default=0.0)
    paper = Column(Boolean, default=True)


class Signal(Base):
    """Genererede handelssignaler (til analyse og debugging)"""
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    symbol = Column(String(20), nullable=False)
    strategy = Column(String(50), nullable=False)
    signal = Column(String(10), nullable=False)
    strength = Column(Float, default=1.0)
    price = Column(Float, nullable=True)
    notes = Column(String(500), nullable=True)


class AccountSnapshot(Base):
    """
    Live konto-snapshot — skrevet af botten efter hver cyklus.
    Dashboard læser herfra i stedet for at kalde Alpaca direkte.
    """
    __tablename__ = "account_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    equity = Column(Float, nullable=False)
    cash = Column(Float, nullable=False)
    buying_power = Column(Float, nullable=False)
    portfolio_value = Column(Float, nullable=False)
    paper = Column(Boolean, default=True)


class PositionSnapshot(Base):
    """
    Live positioner — skrevet af botten efter hver cyklus.
    Dashboard læser herfra i stedet for at kalde Alpaca direkte.
    Alle eksisterende positioner overskrives/slettes og genskrives ved hver cyklus.
    """
    __tablename__ = "position_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    symbol = Column(String(20), nullable=False)
    qty = Column(Float, nullable=False)
    avg_entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    market_value = Column(Float, nullable=False)
    unrealized_pl = Column(Float, nullable=False)
    unrealized_plpc = Column(Float, nullable=False)
    paper = Column(Boolean, default=True)


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
    # Opret system_flags tabel (bruges af kill-switch og risikoprofil)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS system_flags (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT,
                notes TEXT
            )
        """))
        conn.commit()


def get_session() -> Session:
    """Hent en database session"""
    return SessionLocal()


# ------------------------------------------------------------------ #
#  Bot skriver: konto + positioner                                    #
# ------------------------------------------------------------------ #

def save_account_snapshot(
    equity: float,
    cash: float,
    buying_power: float,
    portfolio_value: float,
    paper: bool = True,
) -> None:
    """Gem live konto-state (kaldes af botten efter hver cyklus)."""
    with get_session() as session:
        snap = AccountSnapshot(
            equity=equity,
            cash=cash,
            buying_power=buying_power,
            portfolio_value=portfolio_value,
            paper=paper,
        )
        session.add(snap)
        session.commit()


def save_position_snapshots(
    positions: list[dict],
    paper: bool = True,
) -> None:
    """
    Overskrid alle positioner med det aktuelle sæt.
    `positions` er en liste af dicts med nøgler:
    symbol, qty, avg_entry_price, current_price, market_value,
    unrealized_pl, unrealized_plpc
    """
    now = datetime.utcnow()
    with get_session() as session:
        # Slet alle eksisterende snapshots for denne mode
        session.query(PositionSnapshot).filter(
            PositionSnapshot.paper == paper
        ).delete()

        for p in positions:
            snap = PositionSnapshot(
                timestamp=now,
                symbol=p["symbol"],
                qty=p["qty"],
                avg_entry_price=p["avg_entry_price"],
                current_price=p["current_price"],
                market_value=p["market_value"],
                unrealized_pl=p["unrealized_pl"],
                unrealized_plpc=p["unrealized_plpc"],
                paper=paper,
            )
            session.add(snap)
        session.commit()


# ------------------------------------------------------------------ #
#  Dashboard læser: konto + positioner                                #
# ------------------------------------------------------------------ #

def get_latest_account(paper: bool = True) -> Optional[dict]:
    """
    Hent seneste konto-snapshot fra databasen.
    Returnerer None hvis botten aldrig har kørt eller ingen data er nyere end 24 timer.
    """
    with get_session() as session:
        cutoff = datetime.utcnow() - timedelta(hours=24)
        row = (
            session.query(AccountSnapshot)
            .filter(
                AccountSnapshot.paper == paper,
                AccountSnapshot.timestamp >= cutoff,
            )
            .order_by(AccountSnapshot.timestamp.desc())
            .first()
        )
        if not row:
            return None
        return {
            "equity": row.equity,
            "cash": row.cash,
            "buying_power": row.buying_power,
            "portfolio_value": row.portfolio_value,
            "timestamp": row.timestamp,
        }


def get_latest_positions(paper: bool = True) -> list[dict]:
    """
    Hent seneste positions-snapshots fra databasen.
    Returnerer tom liste hvis ingen positioner eller data er for gammel.
    """
    with get_session() as session:
        cutoff = datetime.utcnow() - timedelta(hours=24)
        rows = (
            session.query(PositionSnapshot)
            .filter(
                PositionSnapshot.paper == paper,
                PositionSnapshot.timestamp >= cutoff,
            )
            .order_by(PositionSnapshot.market_value.desc())
            .all()
        )
        return [
            {
                "symbol": r.symbol,
                "qty": r.qty,
                "avg_entry_price": r.avg_entry_price,
                "current_price": r.current_price,
                "market_value": r.market_value,
                "unrealized_pl": r.unrealized_pl,
                "unrealized_plpc": r.unrealized_plpc,
                "timestamp": r.timestamp,
            }
            for r in rows
        ]


def get_bot_last_seen(paper: bool = True) -> Optional[datetime]:
    """
    Returnerer tidspunktet for det seneste account-snapshot.
    Bruges til at vise "Bot kører" / "Bot stoppet" i dashboard.
    """
    with get_session() as session:
        row = (
            session.query(AccountSnapshot)
            .filter(AccountSnapshot.paper == paper)
            .order_by(AccountSnapshot.timestamp.desc())
            .first()
        )
        return row.timestamp if row else None


# ------------------------------------------------------------------ #
#  Eksisterende hjælpefunktioner                                      #
# ------------------------------------------------------------------ #

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
    with get_session() as session:
        trade = Trade(
            symbol=symbol, side=side, qty=qty, price=price,
            order_id=order_id, strategy=strategy, paper=paper, status=status,
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
    with get_session() as session:
        snap = PortfolioSnapshot(
            total_value=total_value, cash=cash, invested=invested,
            daily_pnl=daily_pnl, daily_pnl_pct=daily_pnl_pct, paper=paper,
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
    with get_session() as session:
        sig = Signal(
            symbol=symbol, strategy=strategy, signal=signal,
            strength=strength, price=price, notes=notes,
        )
        session.add(sig)
        session.commit()
        session.refresh(sig)
        return sig


def get_system_flag(key: str) -> Optional[str]:
    """Hent en system-flag fra databasen."""
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT value FROM system_flags WHERE key = :key LIMIT 1"),
                {"key": key},
            )
            row = result.fetchone()
            return row[0] if row else None
    except Exception:
        return None


def set_system_flag(key: str, value: str, notes: str = "") -> None:
    """Gem en system-flag i databasen."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO system_flags (key, value, updated_at, notes)
                VALUES (:key, :value, :ts, :notes)
                ON CONFLICT(key) DO UPDATE SET
                    value = :value, updated_at = :ts, notes = :notes
            """), {"key": key, "value": value, "ts": datetime.utcnow().isoformat(), "notes": notes})
            conn.commit()
    except Exception:
        pass


if __name__ == "__main__":
    init_db()
    print(f"Database oprettet: {DB_PATH}")
