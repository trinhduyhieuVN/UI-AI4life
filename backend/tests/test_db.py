from sqlalchemy import text

from app import db as dbmod


def test_wal_and_fk(tmp_path):
    eng = dbmod.make_engine(tmp_path / "t.db")
    dbmod.init_db(eng)
    with eng.connect() as c:
        assert c.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert c.execute(text("PRAGMA foreign_keys")).scalar() == 1