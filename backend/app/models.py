from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

ROLE_IDS = "('observer','retail','institutional','compliance','regulator','quant')"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(collation="NOCASE"), unique=True)
    email: Mapped[str] = mapped_column(String, default="")
    password_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, default=now)
    is_demo: Mapped[int] = mapped_column(Integer, default=0)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[str] = mapped_column(String, default=now)
    expires_at: Mapped[str] = mapped_column(String)
    user_agent: Mapped[str] = mapped_column(String, default="")


class Prefs(Base):
    __tablename__ = "prefs"
    __table_args__ = (CheckConstraint(f"role IN {ROLE_IDS}"),)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String, default="retail")
    theme: Mapped[str] = mapped_column(String, default="workbench")
    chart_json: Mapped[str] = mapped_column(String, default="{}")
    future: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[str] = mapped_column(String, default=now)


class WatchlistItem(Base):
    __tablename__ = "watchlist"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("symbols.symbol"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[str] = mapped_column(String, default=now)


class ViewRow(Base):
    __tablename__ = "views"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String)
    config_json: Mapped[str] = mapped_column(String, default="{}")
    created_at: Mapped[str] = mapped_column(String, default=now)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("label IN ('noteworthy','ordinary','uncertain','data_error')"),
        UniqueConstraint("user_id", "event_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    event_id: Mapped[str] = mapped_column(String)
    label: Mapped[str] = mapped_column(String)
    reviewer_name: Mapped[str] = mapped_column(String)
    at: Mapped[str] = mapped_column(String, default=now)


class SymbolRow(Base):
    __tablename__ = "symbols"
    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, default="")
    sector: Mapped[str] = mapped_column(String, default="")
    active: Mapped[int] = mapped_column(Integer, default=1)


class TradingSession(Base):
    __tablename__ = "trading_sessions"
    date: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(String, default="")


class Bar(Base):
    __tablename__ = "bars"
    __table_args__ = (CheckConstraint("minute BETWEEN 0 AND 389"),)
    symbol: Mapped[str] = mapped_column(ForeignKey("symbols.symbol"), primary_key=True)
    session_date: Mapped[str] = mapped_column(ForeignKey("trading_sessions.date"), primary_key=True)
    minute: Mapped[int] = mapped_column(Integer, primary_key=True)
    o: Mapped[float] = mapped_column(Float)
    h: Mapped[float] = mapped_column(Float)
    l: Mapped[float] = mapped_column(Float)
    c: Mapped[float] = mapped_column(Float)
    v: Mapped[int] = mapped_column(Integer)


class SignalEvent(Base):
    __tablename__ = "signal_events"
    __table_args__ = (
        CheckConstraint("type IN ('point','segment')"),
        CheckConstraint("source IN ('demo','live')"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("symbols.symbol"))
    session_date: Mapped[str] = mapped_column(ForeignKey("trading_sessions.date"))
    type: Mapped[str] = mapped_column(String)
    start_idx: Mapped[int] = mapped_column(Integer)
    end_idx: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    alert: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String, default="")
    label: Mapped[str] = mapped_column(String)
    suppressed: Mapped[int] = mapped_column(Integer, default=0)
    suppressed_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    outbox: Mapped[str] = mapped_column(String)
    quality: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    model_version: Mapped[str] = mapped_column(String)
    features_json: Mapped[str] = mapped_column(String, default="{}")
    plain_vi: Mapped[str] = mapped_column(String, default="")
    source: Mapped[str] = mapped_column(String, default="demo")


class OutboxRow(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        CheckConstraint("status IN ('pending','sent','dead_letter','suppressed')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("signal_events.id"), unique=True)
    status: Mapped[str] = mapped_column(String)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[str] = mapped_column(String, default=now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String)
    detail_json: Mapped[str] = mapped_column(String, default="{}")
    at: Mapped[str] = mapped_column(String, default=now)


class ImportRecord(Base):
    __tablename__ = "imports"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String, default="localstorage-backup")
    payload_checksum: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="ok")
    created_at: Mapped[str] = mapped_column(String, default=now)


Index("ix_bars_date_sym", Bar.session_date, Bar.symbol)
Index("ix_sig_date_end", SignalEvent.session_date, SignalEvent.end_idx)
Index("ix_audit_user_at", AuditLog.user_id, AuditLog.at)