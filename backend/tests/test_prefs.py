import json

from fastapi import Depends
from sqlalchemy import select

from app import auth
from app.models import AuditLog, Prefs, User

MATRIX = {
    "observer": {"rail_rw": 403, "views": 403, "sigCSV": 403, "csv": 403, "review": 403, "scope_all": 403, "audit": 403},
    "retail": {"rail_rw": 200, "views": 200, "sigCSV": 403, "csv": 403, "review": 403, "scope_all": 403, "audit": 403},
    "institutional": {"rail_rw": 200, "views": 200, "sigCSV": 200, "csv": 200, "review": 403, "scope_all": 403, "audit": 403},
    "compliance": {"rail_rw": 200, "views": 200, "sigCSV": 200, "csv": 200, "review": 200, "scope_all": 403, "audit": 200},
    "regulator": {"rail_rw": 200, "views": 200, "sigCSV": 200, "csv": 200, "review": 403, "scope_all": 200, "audit": 200},
    "quant": {"rail_rw": 200, "views": 200, "sigCSV": 200, "csv": 200, "review": 403, "scope_all": 403, "audit": 403},
}


def _auth(client, name, role):
    auth._rate.clear()
    assert client.post(
        "/api/v1/auth/register",
        json={"username": name, "password": "password1", "role": role},
    ).status_code == 200
    assert client.post(
        "/api/v1/auth/login", json={"username": name, "password": "password1"}
    ).status_code == 200


def _prefs_row(db, name):
    u = db.scalar(select(User).where(User.username == name))
    return db.get(Prefs, u.id)


def test_future_lock_409(client, db):
    for role in ("compliance", "regulator", "observer"):
        name = "fut_" + role
        _auth(client, name, role)
        r = client.put("/api/v1/prefs", json={"future": False})
        assert r.status_code == 409
        assert _prefs_row(db, name).future == 1
    _auth(client, "fut_retail", "retail")
    assert client.put("/api/v1/prefs", json={"future": False}).status_code == 200
    assert client.get("/api/v1/prefs").json()["future"] is False
    assert _prefs_row(db, "fut_retail").future == 0


def test_role_422(client):
    _auth(client, "rolebad", "retail")
    assert client.put("/api/v1/prefs", json={"role": "admin"}).status_code == 422


def test_blind_not_persisted(client):
    _auth(client, "blindu", "compliance")
    r = client.put("/api/v1/prefs", json={"blind": True, "chart": {"type": "candles"}})
    assert r.status_code == 200
    body = client.get("/api/v1/prefs").json()
    assert "blind" not in body
    assert "blind" not in body["chart"]


def test_caps_matrix(client):
    app = client.app
    from fastapi.routing import APIRoute
    for cap in MATRIX["observer"]:
        def _probe(u=Depends(auth.require_cap(cap))):
            return {"ok": True}
        # Chèn trước mount static catch-all "/" để route probe không bị che;
        # APIRoute tạo tay cần dependency_overrides_provider để nhận override get_db của fixture.
        app.router.routes.insert(-1, APIRoute(f"/api/v1/_probe/{cap}", endpoint=_probe, methods=["GET"], dependency_overrides_provider=app))
    for role, expect in MATRIX.items():
        _auth(client, "cap_" + role, role)
        for cap, code in expect.items():
            r = client.get(f"/api/v1/_probe/{cap}")
            assert r.status_code == code, (role, cap, r.status_code)
            if code == 403:
                assert r.json()["detail"]["cap"] == cap


def test_chart_clamp(client):
    _auth(client, "clampu", "observer")
    r = client.put(
        "/api/v1/prefs",
        json={"chart": {"type": "ha", "tf": "1m", "spd": 9}},
    )
    assert r.status_code == 200
    chart = client.get("/api/v1/prefs").json()["chart"]
    assert chart["type"] == "line"
    assert chart["tf"] == "5m"
    assert chart["spd"] == 3


def test_chart_numeric_clamp(client):
    _auth(client, "clampnum", "quant")
    r = client.put("/api/v1/prefs", json={"chart": {
        "overlays": {"ma1": -5, "ma2": 0},
        "sliders": {"rate": 99, "density": 5, "zoom": 100000, "vol": -3},
        "glow": 250,
    }})
    assert r.status_code == 200
    chart = client.get("/api/v1/prefs").json()["chart"]
    assert chart["overlays"]["ma1"] == 2
    assert chart["overlays"]["ma2"] == 2
    assert chart["sliders"]["rate"] == 12
    assert chart["sliders"]["density"] == 20
    assert chart["sliders"]["zoom"] == 390
    assert chart["sliders"]["vol"] == 0
    assert chart["glow"] == 100
    r = client.put("/api/v1/prefs", json={"chart": {
        "overlays": {"ma1": 1000, "ma2": 9999},
        "sliders": {"rate": -4, "density": 500, "zoom": 0, "vol": 999},
        "glow": -10,
    }})
    assert r.status_code == 200
    chart = client.get("/api/v1/prefs").json()["chart"]
    assert chart["overlays"]["ma1"] == 200
    assert chart["overlays"]["ma2"] == 200
    assert chart["sliders"]["rate"] == 0.2
    assert chart["sliders"]["density"] == 100
    assert chart["sliders"]["zoom"] == 14
    assert chart["sliders"]["vol"] == 46
    assert chart["glow"] == 0


def test_role_change_audit(client, db):
    _auth(client, "audu", "retail")
    assert client.put("/api/v1/prefs", json={"role": "quant"}).status_code == 200
    row = db.scalar(select(AuditLog).where(AuditLog.action == "role_change"))
    assert row is not None
    detail = json.loads(row.detail_json)
    assert detail["from"] == "retail" and detail["to"] == "quant"
    assert client.get("/api/v1/prefs").json()["role"] == "quant"
    assert client.get("/api/v1/auth/me").json()["caps"]["id"] == "quant"


def test_role_change_forces_future(client):
    _auth(client, "forceu", "retail")
    assert client.put("/api/v1/prefs", json={"future": False}).status_code == 200
    assert client.put("/api/v1/prefs", json={"role": "compliance"}).status_code == 200
    assert client.get("/api/v1/prefs").json()["future"] is True