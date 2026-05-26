"""API smoke tests."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from rag.api import app

client = TestClient(app)


def _auth_headers() -> dict[str, str]:
    r = client.post(
        "/api/auth/register",
        json={
            "username": "testuser_tts",
            "password": "secret12",
            "email": "tts@example.com",
        },
    )
    if r.status_code == 400 and "already" in r.json().get("detail", "").lower():
        r = client.post(
            "/api/auth/login",
            json={"username": "testuser_tts", "password": "secret12"},
        )
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_health() -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "tts" in data["features"]
    assert "tts_configured" in data


def test_meta() -> None:
    r = client.get("/api/meta")
    assert r.status_code == 200
    assert len(r.json()["themes"]) >= 4


def test_register_login_me() -> None:
    r = client.post(
        "/api/auth/register",
        json={
            "username": "testuser_api",
            "password": "secret12",
            "email": "test@example.com",
        },
    )
    if r.status_code == 400 and "already" in r.json().get("detail", "").lower():
        r = client.post(
            "/api/auth/login",
            json={"username": "testuser_api", "password": "secret12"},
        )
    assert r.status_code == 200
    token = r.json()["token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "test@example.com"


def test_index_html() -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "Vectorless RAG" in r.text


def test_tts_requires_auth() -> None:
    r = client.post("/api/tts", json={"text": "Hello"})
    assert r.status_code == 401


def test_tts_empty_text_rejected() -> None:
    headers = _auth_headers()
    r = client.post("/api/tts", json={"text": "   "}, headers=headers)
    assert r.status_code == 400


def test_tts_returns_audio() -> None:
    headers = _auth_headers()
    fake = b"RIFF" + b"\x00" * 64
    with patch("rag.api.synthesize_speech", return_value=(fake, "audio/wav")):
        r = client.post("/api/tts", json={"text": "Hello world"}, headers=headers)
    assert r.status_code == 200
    assert r.content == fake
    assert r.headers["content-type"].startswith("audio/wav")
