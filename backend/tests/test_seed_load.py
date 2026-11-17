import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import db as dbmod, seed
from app.models import Bar, OutboxRow, Prefs, SignalEvent, User


def test_load_counts(db):
    counts = seed.load_manifest(db, dbmod.SETTINGS.manifest_path)
    assert counts["symbols"] == 50
    assert counts["sessions"] == 11
    assert counts["bars"] == 214500
    assert counts["signals"] > 0
    assert db.scalar(select(func.count()).select_from(Bar)) == 214500
    assert db.scalar(select(func.count()).select_from(OutboxRow)) == db.scalar(
        select(func.count()).select_from(SignalEvent)
    )


def test_pk_duplicate_bar(db):
    seed.load_manifest(db, dbmod.SETTINGS.manifest_path)
    db.add(Bar(symbol="AAPL", session_date="2026-11-02", minute=0, o=1, h=1, l=1, c=1, v=1))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_role_check(db):
    u = User(username="x", password_hash="argon2id$x")
    db.add(u)
    db.commit()
    db.add(Prefs(user_id=u.id, role="admin"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_ensure_demo(db):
    seed.ensure_demo(db)
    u = db.scalar(select(User).where(User.username == "demo"))
    assert u is not None and u.is_demo == 1
    assert u.password_hash.startswith("argon2id$")
    p = db.scalar(select(Prefs).where(Prefs.user_id == u.id))
    assert p.role == "retail"
    seed.ensure_demo(db)
    assert (
        db.scalar(select(func.count()).select_from(User).where(User.username == "demo"))
        == 1
    )