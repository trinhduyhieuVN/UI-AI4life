import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import auth, db as dbmod


@pytest.fixture()
def db(tmp_path):
    eng = dbmod.make_engine(tmp_path / "test.db")
    dbmod.init_db(eng)
    with sessionmaker(bind=eng, expire_on_commit=False)() as s:
        yield s


@pytest.fixture(autouse=True)
def _clear_rate():
    auth._rate.clear()
    yield
    auth._rate.clear()


@pytest.fixture()
def client(db):
    from app.db import get_db
    from app.main import create_app

    app = create_app()

    def _get():
        yield db

    app.dependency_overrides[get_db] = _get
    with TestClient(app) as c:
        yield c