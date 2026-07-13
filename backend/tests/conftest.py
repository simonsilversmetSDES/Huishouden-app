"""Gedeelde fixtures: in-memory database met seed-data en een ingelogde client."""

from collections.abc import Generator

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.rate_limit import login_limiter
from app.config import Settings, get_settings
from app.database import get_db
from app.main import app
from app.models import Base, User
from app.seed import seed_categories, seed_contexts

TEST_PASSWORD = "geheim123"
TEST_EMAIL = "simon@example.test"


@pytest.fixture
def engine() -> Engine:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # één gedeelde connectie: in-memory db blijft bestaan
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db(engine: Engine) -> Generator[Session, None, None]:
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def seeded_db(db: Session) -> Session:
    """Database met de contexten en seed-categorieën uit app.seed."""
    contexts = seed_contexts(db)
    seed_categories(db, contexts)
    db.add(User(name="Simon", email=TEST_EMAIL, password_hash=PasswordHasher().hash(TEST_PASSWORD)))
    db.commit()
    return db


@pytest.fixture
def client(engine: Engine, seeded_db: Session) -> Generator[TestClient, None, None]:
    settings = Settings(_env_file=None, secret_key="test-secret", session_cookie_secure=False)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db() -> Generator[Session, None, None]:
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


@pytest.fixture
def logged_in(client: TestClient) -> TestClient:
    resp = client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert resp.status_code == 200
    return client
