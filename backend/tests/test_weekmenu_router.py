"""Fase 0 Weekmenu: router geregistreerd onder /api/weekmenu en beveiligd met login."""

from fastapi.testclient import TestClient


def test_ping_vereist_login(client: TestClient) -> None:
    assert client.get("/api/weekmenu/ping").status_code == 401


def test_ping_ingelogd(logged_in: TestClient) -> None:
    resp = logged_in.get("/api/weekmenu/ping")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
