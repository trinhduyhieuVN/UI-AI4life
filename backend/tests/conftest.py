import pytest
from sqlalchemy.orm import sessionmaker

from app import db as dbmod


@pytest.fixture()
def db(tmp_path):
    eng = dbmod.make_engine(tmp_path / "test.db")
    dbmod.init_db(eng)
    with sessionmaker(bind=eng, expire_on_commit=False)() as s:
        yield s