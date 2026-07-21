"""Fotoroute (GET /api/weekmenu/photos/{filename}): strikte naamvalidatie + auth."""

import pytest
from fastapi.testclient import TestClient

from app.weekmenu import photos

PHOTOS_URL = "/api/weekmenu/photos"
VALID_NAME = "a" * 32 + ".jpg"  # uuid4().hex is 32 lowercase-hextekens


@pytest.fixture
def photo_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(photos, "PHOTOS_DIR", tmp_path)
    return tmp_path


def test_foto_wordt_geserveerd_met_cache_header(logged_in: TestClient, photo_dir) -> None:
    (photo_dir / VALID_NAME).write_bytes(b"jpeg-bytes")
    resp = logged_in.get(f"{PHOTOS_URL}/{VALID_NAME}")
    assert resp.status_code == 200
    assert resp.content == b"jpeg-bytes"
    assert resp.headers["content-type"] == "image/jpeg"
    assert "immutable" in resp.headers["cache-control"]


def test_media_type_volgt_extensie(logged_in: TestClient, photo_dir) -> None:
    name = "b" * 32 + ".webp"
    (photo_dir / name).write_bytes(b"webp-bytes")
    resp = logged_in.get(f"{PHOTOS_URL}/{name}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/webp"


def test_ontbrekend_bestand_geeft_404(logged_in: TestClient, photo_dir) -> None:
    resp = logged_in.get(f"{PHOTOS_URL}/{VALID_NAME}")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "not_found"


@pytest.mark.parametrize(
    "filename",
    [
        "evil.txt",  # geen uuid-vorm
        "A" * 32 + ".jpg",  # hoofdletters — uuid4().hex is altijd lowercase
        "a" * 31 + ".jpg",  # te kort
        "a" * 32 + ".exe",  # onbekende extensie
        "..%2F" + "a" * 32 + ".jpg",  # traversal-poging (encoded)
    ],
)
def test_ongeldige_naam_geeft_404(logged_in: TestClient, photo_dir, filename: str) -> None:
    # Ook als er een geldig bestand bestaat, mag een ongeldige naam nooit iets lekken.
    (photo_dir / VALID_NAME).write_bytes(b"jpeg-bytes")
    assert logged_in.get(f"{PHOTOS_URL}/{filename}").status_code == 404


def test_fotoroute_vereist_login(client: TestClient, photo_dir) -> None:
    (photo_dir / VALID_NAME).write_bytes(b"jpeg-bytes")
    assert client.get(f"{PHOTOS_URL}/{VALID_NAME}").status_code == 401
