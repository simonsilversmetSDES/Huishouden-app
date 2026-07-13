"""Tests voor login/logout/me met argon2 en sessie-cookies."""

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.rate_limit import LoginRateLimiter, login_limiter
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
    login_limiter.clear()  # geen doorlopende blokkades tussen tests
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


class TestLoginRateLimit:
    """Brute-force-bescherming: blokkade na te veel mislukte pogingen (default 5)."""

    def test_blokkeert_na_max_pogingen(self, client: TestClient) -> None:
        for _ in range(5):
            assert login(client, password="fout").status_code == 401
        resp = login(client, password="fout")
        assert resp.status_code == 429
        assert resp.json()["detail"] == "Te veel mislukte pogingen — probeer het later opnieuw"
        assert int(resp.headers["Retry-After"]) >= 1

    def test_onbekend_account_zelfde_gedrag(self, client: TestClient) -> None:
        # Zelfde blokkade en melding voor een onbestaand account: geen opsomming.
        for _ in range(5):
            assert login(client, email="spook@example.test", password="x").status_code == 401
        resp = login(client, email="spook@example.test", password="x")
        assert resp.status_code == 429
        assert resp.json()["detail"] == "Te veel mislukte pogingen — probeer het later opnieuw"

    def test_geslaagde_login_reset_teller(self, client: TestClient) -> None:
        for _ in range(4):
            login(client, password="fout")
        assert login(client).status_code == 200  # reset
        assert login(client, password="fout").status_code == 401  # geen 429

    def test_ander_ip_via_cf_header_niet_geblokkeerd(self, client: TestClient) -> None:
        # IP + account "simon" vollopen; ander account vanaf ander IP moet nog kunnen.
        for _ in range(5):
            login(client, password="fout")
        # zelfde IP → dicht, ook voor een ander account
        assert login(client, email="ander@example.test", password="x").status_code == 429
        resp = client.post(
            "/api/auth/login",
            json={"email": "ander@example.test", "password": "x"},
            headers={"CF-Connecting-IP": "203.0.113.7"},
        )
        assert resp.status_code == 401  # ander IP + ander account: gewoon fout wachtwoord


class TestLoginRateLimiterUnit:
    """Backoff-gedrag van de limiter zelf, met een injecteerbare klok."""

    @staticmethod
    def _make() -> tuple[LoginRateLimiter, dict[str, float]]:
        t = {"now": 0.0}
        return LoginRateLimiter(clock=lambda: t["now"]), t

    def _fail(self, limiter: LoginRateLimiter, n: int = 1) -> None:
        for _ in range(n):
            limiter.register_failure(["k"], max_attempts=5, base_block_seconds=30,
                                     max_block_seconds=900)

    def test_blokkade_start_en_loopt_af(self) -> None:
        limiter, t = self._make()
        self._fail(limiter, 4)
        assert limiter.retry_after(["k"]) is None
        self._fail(limiter)  # 5e mislukking → 30 s
        assert limiter.retry_after(["k"]) == 30
        t["now"] = 31.0
        assert limiter.retry_after(["k"]) is None

    def test_backoff_verdubbelt_en_capt(self) -> None:
        limiter, _ = self._make()
        self._fail(limiter, 6)  # 1 extra → 60 s
        assert limiter.retry_after(["k"]) == 60
        self._fail(limiter, 10)  # ver voorbij de cap
        assert limiter.retry_after(["k"]) == 900

    def test_reset_wist_teller(self) -> None:
        limiter, _ = self._make()
        self._fail(limiter, 5)
        limiter.reset(["k"])
        assert limiter.retry_after(["k"]) is None
        self._fail(limiter, 4)  # teller begon echt opnieuw
        assert limiter.retry_after(["k"]) is None


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
