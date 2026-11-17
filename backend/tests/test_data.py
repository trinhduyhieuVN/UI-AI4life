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


def test_import_malformed_credentials(client, db):
    _login(client, "imp_i")
    pack = _pack({
        "bad_kdf_int": _acc("bad_kdf_int", VEC[0], kdf=123),
        "bad_kdf_dollar": _acc("bad_kdf_dollar", VEC[0], kdf="pbkdf2-sha256-150k$evil"),
        "bad_kdf_unknown": _acc("bad_kdf_unknown", VEC[0], kdf="pbkdf2-sha1-999"),
        "bad_salt_hex": _acc("bad_salt_hex", VEC[0], salt="zzzz"),
        "bad_salt_odd": _acc("bad_salt_odd", VEC[0], salt="abc"),
        "bad_hash_hex": _acc("bad_hash_hex", VEC[0], hash="nothex!"),
        "empty_salt": _acc("empty_salt", VEC[0], salt=""),
        "good_g": _acc("good_g", VEC[0]),
    })
    r = client.post("/api/v1/data/import-backup", json=pack)
    assert r.status_code == 200
    assert r.json()["imported"] == 1
    assert r.json()["skipped"] == 7
    for name in ("bad_kdf_int", "bad_kdf_dollar", "bad_kdf_unknown", "bad_salt_hex", "bad_salt_odd", "bad_hash_hex", "empty_salt"):
        assert db.scalar(select(User).where(User.username == name)) is None, name
    auth._rate.clear()
    assert client.post("/api/v1/auth/login", json={"username": "bad_salt_hex", "password": "x"}).status_code == 401


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

def _v2(users):
    return {"app": "nasdaq-replay", "version": 2, "exportedAt": "2026-11-17T00:00:00+00:00", "users": users}


def test_restore_overwrites_current_user(client):
    _login(client, "res_a", "compliance")
    client.put("/api/v1/prefs", json={"chart": {"tf": "15m", "type": "baseline", "sliders": {"zoom": 40}}})
    client.post("/api/v1/watchlist", json={"symbol": "NVDA"})
    pack = client.get("/api/v1/data/backup").json()
    entry = next(u for u in pack["users"] if u["username"] == "res_a")
    for s in client.get("/api/v1/auth/me").json()["watch"]:
        assert client.delete("/api/v1/watchlist/" + s).status_code == 200
    for v in client.get("/api/v1/views").json()["views"]:
        assert client.delete("/api/v1/views/" + str(v["id"])).status_code == 200
    client.put("/api/v1/prefs", json={"chart": {}})
    wiped = client.get("/api/v1/auth/me").json()
    assert wiped["watch"] == [] and wiped["views"] == []
    entry["prefs"]["future"] = False
    r = client.post("/api/v1/data/restore", json=pack)
    assert r.status_code == 200
    after = client.get("/api/v1/auth/me").json()
    assert after["watch"] == entry["watchlist"]
    assert len(after["views"]) == len(entry["views"])
    assert after["prefs"]["future"] is True
    assert after["prefs"]["tf"] == "15m"
    assert after["prefs"]["sliders"]["zoom"] == 40


def test_restore_reviews_and_role_change(client, db):
    _login(client, "res_b", "compliance")
    db.add(TradingSession(date="2026-11-03", label="2026-11-03"))
    db.flush()
    db.add(SignalEvent(
        id="AAPL|2026-11-03|R1", symbol="AAPL", session_date="2026-11-03",
        type="point", start_idx=10, end_idx=10, score=1.0, threshold=1.0,
        alert=0, label="ordinary", outbox="pending", quality="OK",
        model="m", model_version="v",
    ))
    db.commit()
    client.post("/api/v1/reviews", json={"event_id": "AAPL|2026-11-03|R1", "label": "noteworthy"})
    pack = client.get("/api/v1/data/backup").json()
    entry = next(u for u in pack["users"] if u["username"] == "res_b")
    assert entry["reviews"]["AAPL|2026-11-03|R1"]["label"] == "noteworthy"
    client.post("/api/v1/reviews", json={"event_id": "AAPL|2026-11-03|R1", "label": "ordinary"})
    entry["prefs"]["role"] = "regulator"
    assert client.post("/api/v1/data/restore", json=pack).status_code == 200
    me = client.get("/api/v1/auth/me").json()
    assert me["user"]["role"] == "regulator"
    assert me["reviews"]["AAPL|2026-11-03|R1"]["label"] == "noteworthy"
    actions = [a["action"] for a in client.get("/api/v1/audit").json()["audit"]]
    assert "role_change" in actions and "restore_backup" in actions


def test_restore_gates_and_malformed(client):
    _login(client, "res_c", "observer")
    assert client.post("/api/v1/data/restore", json=_v2([])).status_code == 403
    _login(client, "res_d", "retail")
    assert client.post("/api/v1/data/restore", json={"app": "x", "version": 2, "users": []}).status_code == 422
    assert client.post("/api/v1/data/restore", json=_v2([{"username": "someone_else"}])).status_code == 422
    r = client.post("/api/v1/data/restore", json=_v2([
        {"username": "res_d", "prefs": {"role": "admin"}, "watchlist": ["NOPE"], "views": [], "reviews": {}},
    ]))
    assert r.status_code == 200
    me = client.get("/api/v1/auth/me").json()
    assert me["user"]["role"] == "retail"
    assert me["watch"] == []


def test_restore_dedupes_watchlist_and_views(client):
    _login(client, "res_f", "retail")
    pack = _v2([{
        "username": "res_f",
        "prefs": {},
        "watchlist": ["AAPL", "AAPL", "NVDA", "AAPL"],
        "views": [
            {"name": "Trùng", "syms": ["AAPL"]},
            {"name": "Trùng", "syms": ["NVDA"]},
            {"name": "Khác", "syms": []},
        ],
        "reviews": {},
    }])
    r = client.post("/api/v1/data/restore", json=pack)
    assert r.status_code == 200
    assert r.json()["watchlist"] == 2
    assert r.json()["views"] == 2
    me = client.get("/api/v1/auth/me").json()
    assert me["watch"] == ["AAPL", "NVDA"]
    assert [v["name"] for v in me["views"]] == ["Trùng", "Khác"]


def test_me_caps_audit_flag(client):
    _login(client, "res_e", "compliance")
    assert client.get("/api/v1/auth/me").json()["caps"]["audit"] is True
    client.put("/api/v1/prefs", json={"role": "retail"})
    assert client.get("/api/v1/auth/me").json()["caps"]["audit"] is False
