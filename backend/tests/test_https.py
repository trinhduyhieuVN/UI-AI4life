import os
import pathlib
import socket
import ssl
import subprocess
import sys
import time

import httpx
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CA = ROOT / "certs" / "rootCA.pem"
PORT = 8000
BASE = f"https://127.0.0.1:{PORT}"


def _port_free(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) != 0


@pytest.fixture(scope="module")
def https_server(tmp_path_factory):
    if not CA.exists():
        pytest.skip("mkcert rootCA.pem absent — generate certs per docs/OPERATIONS.md")
    if not _port_free(PORT):
        pytest.skip(f"port {PORT} busy")
    db = tmp_path_factory.mktemp("https") / "t.db"
    env = {
        **os.environ,
        "NQ_DB": str(db),
        "NQ_PORT": str(PORT),
        "NQ_HTTPS": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.main"],
        cwd=str(ROOT / "backend"),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    up = False
    for _ in range(40):
        if proc.poll() is not None:
            break
        try:
            with httpx.Client(verify=ssl.create_default_context(cafile=str(CA)), timeout=2) as c:
                c.get(BASE + "/")
            up = True
            break
        except Exception:
            time.sleep(0.25)
    yield up
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_https_serves_frontend(https_server):
    assert https_server, "https server never came up (app.main lacks SSL runner / NQ_HTTPS wiring)"
    with httpx.Client(verify=ssl.create_default_context(cafile=str(CA)), timeout=5) as c:
        r = c.get(BASE + "/")
    assert r.status_code == 200
    assert "nq-root" in r.text


def test_login_cookie_secure_over_https(https_server):
    assert https_server, "https server never came up"
    with httpx.Client(verify=ssl.create_default_context(cafile=str(CA)), timeout=5) as c:
        r = c.post(BASE + "/api/v1/auth/login", json={"username": "demo", "password": "demo1234"})
    assert r.status_code == 200
    cookie = r.headers.get("set-cookie", "")
    assert "nq_session=" in cookie
    assert "Secure" in cookie, f"session cookie missing Secure flag over https: {cookie}"