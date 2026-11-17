import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import auth, db as dbmod, seed
from app.config import SETTINGS
from app.db import get_db
from app.main import create_app

MANIFEST = json.loads(SETTINGS.manifest_path.read_text(encoding="utf-8"))
SIG_HEADER = "symbol,segment_id,timestamp,window_start,score,threshold,alert,reason,suppressed_reason,outbox,quality"
DEFAULT_WATCH = {"AAPL", "NVDA", "MSFT", "TSLA", "AMZN", "META", "AVGO", "AMD"}


@pytest.fixture(scope="module")
def loaded_engine(tmp_path_factory):
    eng = dbmod.make_engine(tmp_path_factory.mktemp("signals") / "s.db")
    dbmod.init_db(eng)
    with sessionmaker(bind=eng)() as s:
        seed.load_manifest(s, SETTINGS.manifest_path)
    return eng


@pytest.fixture()
def sclient(loaded_engine):
    with sessionmaker(bind=loaded_engine, expire_on_commit=False)() as s:
        app = create_app(seed_data=False)

        def _get():
            yield s

        app.dependency_overrides[get_db] = _get
        with TestClient(app) as c:
            yield c


def _login(client, name, role):
    auth._rate.clear()
    client.post("/api/v1/auth/register", json={"username": name, "password": "password1", "role": role})
    assert client.post("/api/v1/auth/login", json={"username": name, "password": "password1"}).status_code == 200


def _sig(client, **params):
    return client.get("/api/v1/signals", params=params)


def test_cursor0_empty(sclient):
    _login(sclient, "sig_a", "retail")
    r = _sig(sclient, symbol="AAPL", date="2026-11-02", tf="1m", cursor=0)
    assert r.status_code == 200
    assert r.json()["signals"] == []


def test_causal_mid(sclient):
    _login(sclient, "sig_b", "retail")
    r = _sig(sclient, symbol="AAPL", date="2026-11-05", tf="1m", cursor=195)
    assert r.status_code == 200
    evs = r.json()["signals"]
    assert len(evs) > 0
    assert all(e["endIdx"] <= 195 for e in evs)
    expect = {e["id"] for e in MANIFEST["signals"]["AAPL|2026-11-05"] if e["endIdx"] <= 195}
    assert {e["id"] for e in evs} == expect
    assert evs == sorted(evs, key=lambda e: (-e["tEnd"], e["sym"]))


def test_back_to_zero(sclient):
    _login(sclient, "sig_c", "retail")
    assert len(_sig(sclient, symbol="AAPL", date="2026-11-05", tf="1m", cursor=195).json()["signals"]) > 0
    assert _sig(sclient, symbol="AAPL", date="2026-11-05", tf="1m", cursor=0).json()["signals"] == []


def test_1d_rule(sclient):
    _login(sclient, "sig_d", "retail")
    r = _sig(sclient, symbol="AAPL", date="2026-11-16", tf="1D", cursor=3)
    assert r.status_code == 200
    evs = r.json()["signals"]
    assert {e["si"] for e in evs} == {0, 1, 2, 3}
    expect = set()
    for d in MANIFEST["sessions"][:4]:
        expect |= {e["id"] for e in MANIFEST["signals"]["AAPL|" + d]}
    assert {e["id"] for e in evs} == expect


def test_scope_all_403(sclient):
    _login(sclient, "sig_e", "retail")
    r = _sig(sclient, scope="all", date="2026-11-16", tf="1m", cursor=389)
    assert r.status_code == 403
    assert r.json()["detail"]["cap"] == "scope_all"
    _login(sclient, "sig_f", "regulator")
    r = _sig(sclient, scope="all", date="2026-11-16", tf="1m", cursor=389)
    assert r.status_code == 200
    evs = r.json()["signals"]
    assert 0 < len(evs) <= 60
    assert any(e["sym"] not in DEFAULT_WATCH for e in evs)


def test_review_compliance_only(sclient):
    _login(sclient, "sig_g", "retail")
    eid = _sig(sclient, symbol="AAPL", date="2026-11-02", tf="1m", cursor=389).json()["signals"][0]["id"]
    r = sclient.post("/api/v1/reviews", json={"event_id": eid, "label": "noteworthy"})
    assert r.status_code == 403
    assert r.json()["detail"]["cap"] == "review"
    _login(sclient, "sig_h", "compliance")
    assert sclient.post("/api/v1/reviews", json={"event_id": eid, "label": "noteworthy"}).status_code == 200
    rv = sclient.get("/api/v1/reviews").json()["reviews"][eid]
    assert rv["label"] == "noteworthy"
    assert rv["reviewer"] == "sig_h"
    assert sclient.post("/api/v1/reviews", json={"event_id": eid, "label": "ordinary"}).status_code == 200
    assert sclient.get("/api/v1/reviews").json()["reviews"][eid]["label"] == "ordinary"


def test_csv_columns(sclient):
    _login(sclient, "sig_i", "quant")
    r = sclient.get("/api/v1/export/signals.csv", params={"symbol": "AAPL", "date": "2026-11-02", "tf": "1m", "cursor": 389, "blind": 0})
    assert r.status_code == 200
    assert r.text.splitlines()[0] == SIG_HEADER
    assert len(r.text.splitlines()) > 1
    r = sclient.get("/api/v1/export/bars.csv", params={"symbol": "AAPL", "date": "2026-11-02", "tf": "5m"})
    assert r.status_code == 200
    assert r.text.splitlines()[0] == "t,o,h,l,c,v"
    assert len(r.text.splitlines()) == 79


def test_blind_blocks_csv(sclient):
    _login(sclient, "sig_j", "compliance")
    params = {"symbol": "AAPL", "date": "2026-11-02", "tf": "1m", "cursor": 389}
    assert sclient.get("/api/v1/export/signals.csv", params=params).status_code == 403
    assert sclient.get("/api/v1/export/signals.csv", params={**params, "blind": 1}).status_code == 403
    assert sclient.get("/api/v1/export/signals.csv", params={**params, "blind": 0}).status_code == 200


def test_export_caps(sclient):
    _login(sclient, "sig_k", "retail")
    r = sclient.get("/api/v1/export/signals.csv", params={"symbol": "AAPL", "date": "2026-11-02", "tf": "1m", "cursor": 389})
    assert r.status_code == 403
    assert r.json()["detail"]["cap"] == "sigCSV"
    _login(sclient, "sig_l", "observer")
    r = sclient.get("/api/v1/export/bars.csv", params={"symbol": "AAPL", "date": "2026-11-02", "tf": "5m"})
    assert r.status_code == 403
    assert r.json()["detail"]["cap"] == "csv"