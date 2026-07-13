"""Tests voor login/logout/me met argon2 en sessie-cookies."""

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.sessions import create_session_value, parse_session_value
from app.config import Settings, get_settings
from app.database import get_db
from app.main import app
from app.models import Base, User

PASSWORD = "geheim123"


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, secret_key="test-secret", session_cookie_secure=False)


@pytest.fixture
def client(settings: Settings):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # één gedeelde connectie: in-memory db blijft bestaan
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)

    with Session(engine) as setup:
        setup.add(
            User(
                name="Simon",
                email="simon@example.test",
                password_hash=PasswordHasher().hash(PASSWORD),
            )
        )
        setup.commit()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def login(client: TestClient, email: str = "simon@example.test", password: str = PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


class TestLogin:
    def test_success_sets_cookie_and_me_works(self, client: TestClient) -> None:
        resp = login(client)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Simon"
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json() == {"id": 1, "name": "Simon", "email": "simon@example.test"}

    def test_wrong_password_generic_401(self, client: TestClient) -> None:
        resp = login(client, password="fout")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Ongeldige inloggegevens"

    def test_unknown_email_same_401(self, client: TestClient) -> None:
        resp = login(client, email="onbekend@example.test")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Ongeldige inloggegevens"

    def test_no_password_hash_leak(self, client: TestClient) -> None:
        resp = login(client)
        assert "password" not in resp.text
        assert "argon2" not in resp.text


class TestSessionProtection:
    def test_me_without_cookie_401(self, client: TestClient) -> None:
        assert client.get("/api/auth/me").status_code == 401

    def test_tampered_cookie_401(self, client: TestClient, settings: Settings) -> None:
        login(client)
        client.cookies.set(settings.session_cookie_name, "geknoei-met-de-cookie")
        assert client.get("/api/auth/me").status_code == 401

    def test_logout_clears_session(self, client: TestClient) -> None:
        login(client)
        assert client.get("/api/auth/me").status_code == 200
        client.post("/api/auth/logout")
        assert client.get("/api/auth/me").status_code == 401


class TestSessionValue:
    def test_roundtrip(self, settings: Settings) -> None:
        value = create_session_value(user_id=7, settings=settings)
        assert parse_session_value(value, settings) == 7

    def test_expired_returns_none(self, settings: Settings) -> None:
        value = create_session_value(user_id=7, settings=settings)
        assert parse_session_value(value, settings, max_age_seconds=-1) is None

    def test_garbage_returns_none(self, settings: Settings) -> None:
        assert parse_session_value("rommel", settings) is None

    def test_other_secret_rejected(self, settings: Settings) -> None:
        value = create_session_value(user_id=7, settings=settings)
        other = Settings(_env_file=None, secret_key="ander-secret")
        assert parse_session_value(value, other) is None


class TestHealth:
    def test_health_is_public(self, client: TestClient) -> None:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestSecretKeyGuard:
    """Buiten development weigert de app een onveilige SECRET_KEY (startup-guard)."""

    def test_production_weigert_default_key(self) -> None:
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            Settings(_env_file=None, app_env="production")

    def test_production_weigert_lege_key(self) -> None:
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            Settings(_env_file=None, app_env="production", secret_key="")

    def test_production_weigert_korte_key(self) -> None:
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            Settings(_env_file=None, app_env="production", secret_key="kort-maar-niet-default")

    def test_production_aanvaardt_lange_key(self) -> None:
        settings = Settings(_env_file=None, app_env="production", secret_key="x" * 32)
        assert settings.secret_key == "x" * 32

    def test_development_laat_default_toe(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.app_env == "development"
