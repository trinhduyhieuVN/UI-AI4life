import json
from pathlib import Path

from sqlalchemy import func, select

from app import auth
from app.models import ImportRecord, SignalEvent, TradingSession, User, WatchlistItem

VEC = json.loads(
    (Path(__file__).resolve().parents[2] / "tools" / "legacy_vector.json").read_text(encoding="utf-8")
)


def _login(client, name, role="retail", pw="password1"):
    auth._rate.clear()
    client.post("/api/v1/auth/register", json={"username": name, "password": "password1", "role": role})
    assert client.post("/api/v1/auth/login", json={"username": name, "password": pw}).status_code == 200


def _acc(name, vec, prefs=None, **extra):
    a = {
        "id": "u-" + name, "name": name, "email": name + "@x.local",
        "salt": vec["salt"], "hash": vec["hash"], "kdf": vec["kdf"],
        "prefs": prefs if prefs is not None else {},
    }
    a.update(extra)
    return a


def _pack(users):
    return {"app": "nasdaq-replay", "version": 1, "exportedAt": "2026-11-17T00:00:00+00:00", "db": {"users": users, "session": None}}


def test_import_all_accounts(client, db):
    _login(client, "imp_a")
    pack = _pack({
        "old_a": _acc("old_a", VEC[0], {"role": "quant", "future": False, "watch": ["AAPL", "NVDA"], "tf": "15m", "type": "ha", "spd": 2}),
        "old_b": _acc("old_b", VEC[1], {"role": "compliance", "future": False}),
        "old_c": _acc("old_c", VEC[0], {"role": "retail"}),
    })
    r = client.post("/api/v1/data/import-backup", json=pack)
    assert r.status_code == 200
    assert r.json()["imported"] == 3
    for name in ("old_a", "old_b", "old_c"):
        auth._rate.clear()
        assert client.post("/api/v1/auth/login", json={"username": name, "password": VEC[0]["pw"]}).status_code == 200
        if name == "old_b":
            assert client.get("/api/v1/prefs").json()["future"] is True
        if name == "old_a":
            me = client.get("/api/v1/auth/me").json()
            assert me["user"]["role"] == "quant"
            assert me["prefs"]["tf"] == "15m"
            assert "NVDA" in me["watch"]
        client.post("/api/v1/auth/logout")


def test_import_idempotent(client, db):
    _login(client, "imp_b")
    pack = _pack({"old_d": _acc("old_d", VEC[0]), "old_e": _acc("old_e", VEC[1])})
    assert client.post("/api/v1/data/import-backup", json=pack).json()["imported"] == 2
    users_before = db.scalar(select(func.count(User.id)))
    watch_before = db.scalar(select(func.count()).select_from(WatchlistItem))
    r = client.post("/api/v1/data/import-backup", json=pack)
    assert r.json()["imported"] == 0
    assert r.json()["skipped"] == 2
    assert db.scalar(select(func.count(User.id))) == users_before
    assert db.scalar(select(func.count()).select_from(WatchlistItem)) == watch_before
    assert db.scalar(select(func.count(ImportRecord.id))) == 2


def test_import_malformed(client, db):
    _login(client, "imp_c")
    bad_salt = _acc("bad_salt", VEC[0])
    del bad_salt["salt"]
    bad_hash = _acc("bad_hash", VEC[0])
    del bad_hash["hash"]
    pack = _pack({
        "bad_salt": bad_salt,
        "bad_hash": bad_hash,
        "good_f": _acc("good_f", VEC[0], {"role": "admin"}),
    })
    r = client.post("/api/v1/data/import-backup", json=pack)
    assert r.status_code == 200
    assert r.json()["imported"] == 1
    assert r.json()["skipped"] == 2
    auth._rate.clear()
    assert client.post("/api/v1/auth/login", json={"username": "good_f", "password": VEC[0]["pw"]}).status_code == 200
    me = client.get("/api/v1/auth/me").json()
    assert me["user"]["role"] == "retail"
    assert "AAPL" in me["watch"]
    assert len(me["views"]) == 3


def test_backup_data_only(client):
    _login(client, "imp_d", "compliance")
    r = client.get("/api/v1/data/backup")
    assert r.status_code == 200
    body = r.json()
    assert body["app"] == "nasdaq-replay"
    assert body["version"] == 2
    text = r.text
    for banned in ('"hash"', '"salt"', '"blind"', '"score"', '"password"'):
        assert banned not in text
    me = next(u for u in body["users"] if u["username"] == "imp_d")
    assert {"username", "email", "prefs", "watchlist", "views", "reviews"} <= set(me)
    assert "AAPL" in me["watchlist"]


def test_audit_gates(client):
    _login(client, "imp_e", "retail")
    r = client.get("/api/v1/audit")
    assert r.status_code == 403
    assert r.json()["detail"]["cap"] == "audit"
    _login(client, "imp_f", "compliance")
    assert client.get("/api/v1/audit").status_code == 200


def test_audit_actions(client, db):
    _login(client, "imp_g", "quant")
    db.add(TradingSession(date="2026-11-02", label="2026-11-02"))
    db.flush()
    db.add(SignalEvent(
        id="AAPL|2026-11-02|E1", symbol="AAPL", session_date="2026-11-02",
        type="point", start_idx=372, end_idx=372, score=1.0, threshold=1.0,
        alert=0, label="ordinary", outbox="pending", quality="OK",
        model="m", model_version="v",
    ))
    db.commit()
    client.get("/api/v1/export/bars.csv", params={"symbol": "AAPL", "date": "2026-11-02", "tf": "5m"})
    client.post("/api/v1/data/import-backup", json=_pack({"old_h": _acc("old_h", VEC[0])}))
    client.put("/api/v1/prefs", json={"role": "compliance"})
    client.post("/api/v1/reviews", json={"event_id": "AAPL|2026-11-02|E1", "label": "ordinary"})
    actions = {a["action"] for a in client.get("/api/v1/audit").json()["audit"]}
    assert {"login", "export", "import_backup", "role_change", "review"} <= actions


def test_data_gate_observer(client):
    _login(client, "imp_h", "observer")
    assert client.get("/api/v1/data/backup").status_code == 403
    r = client.post("/api/v1/data/import-backup", json=_pack({}))
    assert r.status_code == 403
    assert r.json()["detail"]["cap"] == "dataManager"