from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import SETTINGS


class Base(DeclarativeBase):
    pass


def make_engine(db_path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    eng = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return eng


engine = make_engine(SETTINGS.db_path)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as s:
        yield s


def init_db(eng=None):
    eng = eng if eng is not None else engine
    Base.metadata.create_all(eng)
    with eng.connect() as c:
        c.execute(text("PRAGMA journal_mode=WAL"))
        c.commit()