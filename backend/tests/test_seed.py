"""Tests voor de idempotente seed (contexten, categorieën, rekeningen, users)."""

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Account, Base, Category, Context, User
from app.models.enums import AccountType, Bank, CategoryType
from app.seed import seed_all


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        simon_email="simon@example.test",
        simon_password_hash="$argon2id$fake-hash-simon",
        jozefien_email="jozefien@example.test",
        jozefien_password_hash="$argon2id$fake-hash-jozefien",
    )


def counts(session: Session) -> dict[str, int]:
    return {
        "contexts": session.scalar(select(func.count(Context.id))) or 0,
        "categories": session.scalar(select(func.count(Category.id))) or 0,
        "accounts": session.scalar(select(func.count(Account.id))) or 0,
        "users": session.scalar(select(func.count(User.id))) or 0,
    }


def test_seed_creates_expected_rows(session: Session, settings: Settings) -> None:
    seed_all(session, settings)
    assert counts(session) == {
        "contexts": 3,
        "categories": 63,  # 21 categorieën × 3 contexten
        "accounts": 2,
        "users": 2,
    }


def test_seed_is_idempotent(session: Session, settings: Settings) -> None:
    seed_all(session, settings)
    first = counts(session)
    seed_all(session, settings)
    assert counts(session) == first


def test_contexts(session: Session, settings: Settings) -> None:
    seed_all(session, settings)
    names = set(session.scalars(select(Context.name)))
    assert names == {"Gemeenschappelijk", "Simon", "Jozefien"}


def test_categories_per_context(session: Session, settings: Settings) -> None:
    seed_all(session, settings)
    for context_name in ("Gemeenschappelijk", "Simon", "Jozefien"):
        ctx = session.scalars(select(Context).where(Context.name == context_name)).one()
        cats = session.scalars(select(Category).where(Category.context_id == ctx.id)).all()
        by_type = {t: [c for c in cats if c.type == t] for t in CategoryType}
        assert len(by_type[CategoryType.INKOMEN]) == 5
        assert len(by_type[CategoryType.UITGAVEN]) == 14
        assert len(by_type[CategoryType.SPAREN]) == 2
        # Spec-volgorde bewaard via sort_order
        uitgaven = sorted(by_type[CategoryType.UITGAVEN], key=lambda c: c.sort_order)
        assert uitgaven[0].name == "Lening"
        assert uitgaven[-1].name == "Katten"


def test_accounts(session: Session, settings: Settings) -> None:
    seed_all(session, settings)
    kbc = session.scalars(select(Account).where(Account.bank == Bank.KBC)).one()
    fortis = session.scalars(select(Account).where(Account.bank == Bank.FORTIS)).one()
    assert kbc.context.name == "Gemeenschappelijk"
    assert kbc.type == AccountType.ZICHT
    assert fortis.context.name == "Simon"
    assert fortis.type == AccountType.ZICHT


def test_users_from_settings(session: Session, settings: Settings) -> None:
    seed_all(session, settings)
    simon = session.scalars(select(User).where(User.name == "Simon")).one()
    assert simon.email == "simon@example.test"
    assert simon.password_hash == "$argon2id$fake-hash-simon"


def test_user_hash_updated_on_change(session: Session, settings: Settings) -> None:
    seed_all(session, settings)
    settings.simon_password_hash = "$argon2id$nieuwe-hash"
    seed_all(session, settings)
    simon = session.scalars(select(User).where(User.name == "Simon")).one()
    assert simon.password_hash == "$argon2id$nieuwe-hash"
    assert counts(session)["users"] == 2


def test_users_skipped_when_env_empty(session: Session) -> None:
    empty = Settings(_env_file=None)
    seed_all(session, empty)
    assert counts(session)["users"] == 0
    # Contexten/categorieën/rekeningen worden wél geseed
    assert counts(session)["contexts"] == 3
