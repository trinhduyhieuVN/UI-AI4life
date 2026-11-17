import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import db as dbmod, seed
from app.config import SETTINGS
from app.db import get_db
from app.main import create_app

MANIFEST = json.loads(SETTINGS.manifest_path.read_text(encoding="utf-8"))


def _sess_utc_ms(date):
    y, m, d = (int(x) for x in date.split("-"))
    return int(datetime(y, m, d, 14, 30, tzinfo=timezone.utc).timestamp() * 1000)


@pytest.fixture(scope="module")
def loaded_engine(tmp_path_factory):
    eng = dbmod.make_engine(tmp_path_factory.mktemp("market") / "m.db")
    dbmod.init_db(eng)
    with sessionmaker(bind=eng)() as s:
        seed.load_manifest(s, SETTINGS.manifest_path)
    return eng


@pytest.fixture()
def mclient(loaded_engine):
    with sessionmaker(bind=loaded_engine, expire_on_commit=False)() as s:
        app = create_app(seed_data=False)

        def _get():
            yield s

        app.dependency_overrides[get_db] = _get
        with TestClient(app) as c:
            c.post("/api/v1/auth/register", json={"username": "mkt_probe", "password": "password1", "role": "retail"})
            assert c.post("/api/v1/auth/login", json={"username": "mkt_probe", "password": "password1"}).status_code == 200
            yield c


def test_aggregate_5m(mclient):
    r = mclient.get("/api/v1/bars", params={"symbol": "AAPL", "date": "2026-11-02", "tf": "5m"})
    assert r.status_code == 200
    bars = r.json()["bars"]
    m1 = MANIFEST["bars"]["AAPL"]["2026-11-02"]
    assert len(bars) == 78
    for i, b in enumerate(bars):
        chunk = m1[i * 5:(i + 1) * 5]
        assert b["t"] == chunk[0]["t"]
        assert b["o"] == chunk[0]["o"]
        assert b["h"] == max(x["h"] for x in chunk)
        assert b["l"] == min(x["l"] for x in chunk)
        assert b["c"] == chunk[-1]["c"]
        assert b["v"] == sum(x["v"] for x in chunk)


def test_1d(mclient):
    r = mclient.get("/api/v1/bars", params={"symbol": "AAPL", "date": "2026-11-16", "tf": "1D"})
    assert r.status_code == 200
    bars = r.json()["bars"]
    assert len(bars) == 11
    for i, d in enumerate(MANIFEST["sessions"]):
        st = MANIFEST["stats"]["AAPL"][d]
        assert bars[i]["day"] == d
        assert bars[i]["t"] == _sess_utc_ms(d)
        assert bars[i]["o"] == st["open"]
        assert bars[i]["h"] == st["high"]
        assert bars[i]["l"] == st["low"]
        assert bars[i]["c"] == st["close"]
        assert bars[i]["v"] == st["vol"]


def test_tf_422(mclient):
    r = mclient.get("/api/v1/bars", params={"symbol": "AAPL", "date": "2026-11-02", "tf": "7m"})
    assert r.status_code == 422


def test_unknown_symbol_404(mclient):
    r = mclient.get("/api/v1/bars", params={"symbol": "NOPE", "date": "2026-11-02", "tf": "5m"})
    assert r.status_code == 404


def test_symbols_sessions(mclient):
    syms = mclient.get("/api/v1/symbols").json()["symbols"]
    sess = mclient.get("/api/v1/sessions").json()["sessions"]
    assert len(syms) == 50
    assert sess == MANIFEST["sessions"]
    assert {"symbol", "name", "sector"} <= set(syms[0])