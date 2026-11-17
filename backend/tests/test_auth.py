import json
from pathlib import Path

from sqlalchemy import select

from app.models import Session as SessionRow, User

VEC = json.loads(
    (Path(__file__).resolve().parents[2] / "tools" / "legacy_vector.json").read_text(
        encoding="utf-8"
    )
)


def _register(client, name, role="retail"):
    return client.post(
        "/api/v1/auth/register",
        json={"username": name, "password": "password1", "role": role},
    )


def _login(client, name, pw="password1", **kw):
    return client.post("/api/v1/auth/login", json={"username": name, "password": pw}, **kw)


def test_register_login_me_logout(client):
    assert _register(client, "probe_a").status_code == 200
    assert _login(client, "probe_a").status_code == 200
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["user"]["username"] == "probe_a"
    assert body["user"]["role"] == "retail"
    assert "AAPL" in body["watch"]
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_wrong_password(client):
    _register(client, "probe_b")
    assert _login(client, "probe_b", "wrong-pass").status_code == 401


def test_legacy_upgrade(client, db):
    for i, v in enumerate(VEC):
        db.add(
            User(
                username=f"legacy{i}",
                password_hash="pbkdf2$" + v["kdf"] + "$" + v["salt"] + "$" + v["hash"],
            )
        )
    db.commit()
    for i, v in enumerate(VEC):
        assert _login(client, f"legacy{i}", v["pw"]).status_code == 200
        u = db.scalar(select(User).where(User.username == f"legacy{i}"))
        db.refresh(u)
        assert u.password_hash.startswith("argon2id$")
        client.post("/api/v1/auth/logout")
        assert _login(client, f"legacy{i}", v["pw"]).status_code == 200
        client.post("/api/v1/auth/logout")


def test_rate_limit_ignores_xff(client):
    _register(client, "probe_c")
    for i in range(5):
        r = _login(client, "probe_c", "wrong", headers={"X-Forwarded-For": f"10.0.0.{i}"})
        assert r.status_code == 401
    r = _login(client, "probe_c", "wrong", headers={"X-Forwarded-For": "10.9.9.9"})
    assert r.status_code == 429


def test_session_expiry(client, db):
    _register(client, "probe_d")
    _login(client, "probe_d")
    row = db.scalar(select(SessionRow))
    row.expires_at = "2000-01-01T00:00:00+00:00"
    db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401