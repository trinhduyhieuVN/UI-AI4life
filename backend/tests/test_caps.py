from app import auth


def _auth(client, name, role):
    auth._rate.clear()
    assert client.post(
        "/api/v1/auth/register",
        json={"username": name, "password": "password1", "role": role},
    ).status_code == 200
    assert client.post(
        "/api/v1/auth/login", json={"username": name, "password": "password1"}
    ).status_code == 200


def test_observer_watchlist_403(client):
    _auth(client, "obs_w", "observer")
    r = client.post("/api/v1/watchlist", json={"symbol": "AAPL"})
    assert r.status_code == 403
    assert r.json()["detail"]["cap"] == "rail_rw"
    assert client.delete("/api/v1/watchlist/AAPL").status_code == 403
    assert client.put("/api/v1/watchlist/order", json={"symbols": []}).status_code == 403


def test_observer_views_403(client):
    _auth(client, "obs_v", "observer")
    r = client.post("/api/v1/views", json={"name": "X", "config": {}})
    assert r.status_code == 403
    assert r.json()["detail"]["cap"] == "views"
    assert client.get("/api/v1/views").status_code == 403


def test_watchlist_roundtrip(client):
    _auth(client, "ret_w", "retail")
    assert client.delete("/api/v1/watchlist/TSLA").status_code == 200
    assert "TSLA" not in client.get("/api/v1/watchlist").json()["watch"]
    assert client.post("/api/v1/watchlist", json={"symbol": "TSLA"}).status_code == 200
    watch = client.get("/api/v1/watchlist").json()["watch"]
    assert watch[-1] == "TSLA"
    order = list(reversed(watch))
    assert client.put("/api/v1/watchlist/order", json={"symbols": order}).status_code == 200
    assert client.get("/api/v1/watchlist").json()["watch"] == order


def test_watchlist_errors(client):
    _auth(client, "ret_we", "retail")
    assert client.delete("/api/v1/watchlist/NOPE").status_code == 404
    assert client.post("/api/v1/watchlist", json={"symbol": "NOPE"}).status_code == 404
    assert client.post("/api/v1/watchlist", json={"symbol": "AAPL"}).status_code == 409
    assert client.put("/api/v1/watchlist/order", json={"symbols": ["AAPL"]}).status_code == 422


def test_views_crud(client):
    _auth(client, "ret_v", "retail")
    r = client.post("/api/v1/views", json={"name": "Thử", "config": {"symbols": ["AAPL"], "tf": "5m"}})
    assert r.status_code == 200
    vid = r.json()["id"]
    views = client.get("/api/v1/views").json()["views"]
    assert any(v["id"] == vid and v["name"] == "Thử" for v in views)
    assert client.put(f"/api/v1/views/{vid}", json={"name": "Đổi", "config": {"tf": "1m"}}).status_code == 200
    v = next(v for v in client.get("/api/v1/views").json()["views"] if v["id"] == vid)
    assert v["name"] == "Đổi"
    assert v["config"]["tf"] == "1m"
    assert client.delete(f"/api/v1/views/{vid}").status_code == 200
    assert client.delete(f"/api/v1/views/{vid}").status_code == 404


def test_views_ownership(client):
    _auth(client, "own_a", "retail")
    vid = client.post("/api/v1/views", json={"name": "A", "config": {}}).json()["id"]
    _auth(client, "own_b", "retail")
    assert client.put(f"/api/v1/views/{vid}", json={"name": "B"}).status_code == 404
    assert client.delete(f"/api/v1/views/{vid}").status_code == 404