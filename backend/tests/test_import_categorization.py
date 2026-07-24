"""Tests voor de extra categorisatie-lagen bovenop de regelengine (services/
import_categorization.py + integratie in bank_import.build_preview).

Laag 2 (historiek) is deterministisch en zonder netwerk. Laag 3 (AI) wordt getest
met een gemockte Claude-client, zoals test_weekmenu_ingredient_categorization.py.
"""

import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import anthropic
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Category, Transaction
from app.models.enums import Categorization
from app.seed import seed_accounts, seed_contexts, seed_rules
from app.services import bank_import, import_categorization
from app.services.bank_import import build_preview
from app.services.import_categorization import (
    TxCandidate,
    build_history_resolver,
    suggest_categories_ai,
)
from tests.csv_fixtures import FORTIS_ACCOUNT, KBC_ACCOUNT, kbc_card_row, kbc_csv, kbc_row

KBC_SPAAR = "BE55666677778888"
FORTIS_SPAAR = "BE77888899990000"
JOZEFIEN_ZICHT = "BE11222233334444"
GEMEENSCHAPPELIJK = 1  # context-id van de KBC-zichtrekening (zie seed)


@pytest.fixture
def import_db(seeded_db: Session) -> Session:
    """seeded_db + rekeningen mét IBAN's en de seed-regels (zie test_bank_import)."""
    settings = Settings(
        _env_file=None,
        account_iban_kbc_zicht=KBC_ACCOUNT,
        account_iban_kbc_spaar=KBC_SPAAR,
        account_iban_fortis_zicht=FORTIS_ACCOUNT,
        account_iban_fortis_spaar=FORTIS_SPAAR,
        account_iban_jozefien_zicht=JOZEFIEN_ZICHT,
    )
    contexts = seed_contexts(seeded_db)
    seed_accounts(seeded_db, contexts, settings)
    seed_rules(seeded_db, contexts)
    seeded_db.commit()
    return seeded_db


def _settings(**overrides) -> Settings:
    """Settings zonder .env; AI standaard uit zodat er nooit per ongeluk netwerk is."""
    base = {"_env_file": None, "import_ai_categorization_enabled": False}
    base.update(overrides)
    return Settings(**base)


def _cat(db: Session, name: str, context_id: int = GEMEENSCHAPPELIJK) -> Category:
    return db.scalars(
        select(Category).where(Category.context_id == context_id, Category.name == name)
    ).one()


def _add_history(
    db: Session,
    category: Category,
    *,
    iban: str | None = None,
    name: str | None = None,
    amount: str = "-10.00",
    tag: str = "",
) -> None:
    db.add(
        Transaction(
            context_id=GEMEENSCHAPPELIJK,
            date=date(2026, 1, 1),
            amount=Decimal(amount),
            type=category.type,
            counterparty_iban=iban,
            counterparty_name=name,
            category_id=category.id,
            categorization=Categorization.MANUAL,
            is_internal_transfer=False,
            import_hash=f"hist-{category.name}-{iban or name}-{tag}",
        )
    )
    db.commit()


class _FakeMessages:
    """Mini-stub van client.messages, zoals in de weekmenu-tests."""

    def __init__(self, reply: str | None = None, error: Exception | None = None):
        self.reply = reply
        self.error = error
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.reply)])


def _mock_client(monkeypatch: pytest.MonkeyPatch, **kwargs) -> _FakeMessages:
    messages = _FakeMessages(**kwargs)
    monkeypatch.setattr(
        import_categorization, "_client", lambda settings: SimpleNamespace(messages=messages)
    )
    return messages


# ── Laag 2: historiek (deterministisch) ──────────────────────────────────────


class TestHistoryResolver:
    def test_iban_hergebruikt_dominante_categorie(self, import_db: Session) -> None:
        boodschappen = _cat(import_db, "Boodschappen")
        _add_history(import_db, boodschappen, iban="BE12345678901234")
        resolver = build_history_resolver(import_db, GEMEENSCHAPPELIJK)
        hit = resolver.resolve(
            TxCandidate(counterparty_name=None, counterparty_iban="BE12 3456 7890 1234",
                        description=None, amount_cents=-500)
        )
        assert hit is not None and hit.id == boodschappen.id

    def test_naam_wanneer_geen_iban(self, import_db: Session) -> None:
        cadeaus = _cat(import_db, "Cadeaus")
        _add_history(import_db, cadeaus, name="Zeldzame Winkel BV")
        resolver = build_history_resolver(import_db, GEMEENSCHAPPELIJK)
        hit = resolver.resolve(
            TxCandidate(counterparty_name="ZELDZAME WINKEL BV", counterparty_iban=None,
                        description=None, amount_cents=-500)
        )
        assert hit is not None and hit.id == cadeaus.id

    def test_iban_wint_van_naam(self, import_db: Session) -> None:
        boodschappen = _cat(import_db, "Boodschappen")
        cadeaus = _cat(import_db, "Cadeaus")
        _add_history(import_db, cadeaus, name="Dubbel BV")
        _add_history(import_db, boodschappen, iban="BE99999999999999")
        resolver = build_history_resolver(import_db, GEMEENSCHAPPELIJK)
        hit = resolver.resolve(
            TxCandidate(counterparty_name="DUBBEL BV", counterparty_iban="BE99999999999999",
                        description=None, amount_cents=-100)
        )
        assert hit is not None and hit.id == boodschappen.id  # IBAN is specifieker

    def test_dominante_categorie_bij_meerdere(self, import_db: Session) -> None:
        boodschappen = _cat(import_db, "Boodschappen")
        cadeaus = _cat(import_db, "Cadeaus")
        _add_history(import_db, boodschappen, iban="BE55", tag="a")
        _add_history(import_db, boodschappen, iban="BE55", tag="b")
        _add_history(import_db, cadeaus, iban="BE55", tag="c")
        resolver = build_history_resolver(import_db, GEMEENSCHAPPELIJK)
        hit = resolver.resolve(
            TxCandidate(counterparty_name=None, counterparty_iban="BE55",
                        description=None, amount_cents=-1)
        )
        assert hit is not None and hit.id == boodschappen.id

    def test_gedeactiveerde_categorie_telt_niet(self, import_db: Session) -> None:
        cadeaus = _cat(import_db, "Cadeaus")
        _add_history(import_db, cadeaus, iban="BE42")
        cadeaus.active = False
        import_db.commit()
        resolver = build_history_resolver(import_db, GEMEENSCHAPPELIJK)
        assert resolver.resolve(
            TxCandidate(counterparty_name=None, counterparty_iban="BE42",
                        description=None, amount_cents=-1)
        ) is None

    def test_geen_match_geeft_none(self, import_db: Session) -> None:
        resolver = build_history_resolver(import_db, GEMEENSCHAPPELIJK)
        assert resolver.resolve(
            TxCandidate(counterparty_name="ONBEKEND", counterparty_iban="BE00",
                        description=None, amount_cents=-1)
        ) is None


# ── Integratie in build_preview ──────────────────────────────────────────────


class TestBuildPreviewLagen:
    def test_historiek_vult_categorie_in(
        self, import_db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        boodschappen = _cat(import_db, "Boodschappen")
        _add_history(import_db, boodschappen, name="NOVEL SHOP")
        # AI-laag moet niet aangesproken worden voor een historiek-hit:
        monkeypatch.setattr(bank_import, "suggest_categories_ai", lambda *a, **k: {})
        content = kbc_csv(
            [kbc_row(bedrag="-12,00", omschrijving="BETALING", tegenpartij_naam="NOVEL SHOP")]
        )
        (row,) = build_preview(import_db, "kbc.csv", content, _settings()).rows
        assert row.suggestion_source == "history"
        assert row.suggested_category_name == "Boodschappen"

    def test_regel_wint_van_historiek(
        self, import_db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # COLRUYT matcht een seed-regel → Boodschappen. Historiek zou naar Cadeaus wijzen,
        # maar de regel heeft voorrang: laag 2 wordt niet eens geraadpleegd.
        _add_history(import_db, _cat(import_db, "Cadeaus"), name="COLRUYT")
        monkeypatch.setattr(bank_import, "suggest_categories_ai", lambda *a, **k: {})
        content = kbc_csv([kbc_card_row(merchant="3815 COLRUYT SINT-AMAN", bedrag="-9,66")])
        (row,) = build_preview(import_db, "kbc.csv", content, _settings()).rows
        assert row.suggestion_source == "rule"
        assert row.suggested_category_name == "Boodschappen"
        assert row.matched_rule_id is not None

    def test_ai_alleen_voor_openstaande_rijen(
        self, import_db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """De AI-laag krijgt enkel rijen die noch regel noch historiek dekten."""
        boodschappen = _cat(import_db, "Boodschappen")
        cadeaus = _cat(import_db, "Cadeaus")
        _add_history(import_db, boodschappen, name="NOVEL SHOP")

        captured: dict = {}

        def fake_ai(candidates, categories, settings, examples=None):
            captured["candidates"] = candidates
            return {0: cadeaus.id}  # de enige openstaande rij → Cadeaus

        monkeypatch.setattr(bank_import, "suggest_categories_ai", fake_ai)
        content = kbc_csv(
            [
                kbc_row(afschrift="02026001", bedrag="-12,00", omschrijving="BETALING",
                        tegenpartij_naam="NOVEL SHOP"),  # historiek
                kbc_row(afschrift="02026002", bedrag="-30,00", omschrijving="BETALING",
                        tegenpartij_naam="TOTAAL ONBEKEND"),  # openstaand → AI
            ]
        )
        preview = build_preview(import_db, "kbc.csv", content, _settings())
        # Slechts één kandidaat naar de AI-laag: de openstaande rij.
        assert len(captured["candidates"]) == 1
        assert captured["candidates"][0].counterparty_name == "TOTAAL ONBEKEND"
        sources = {r.suggested_category_name: r.suggestion_source for r in preview.rows}
        assert sources["Boodschappen"] == "history"
        assert sources["Cadeaus"] == "ai"

    def test_interne_overschrijving_niet_naar_ai(
        self, import_db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        called = False

        def fake_ai(*a, **k):
            nonlocal called
            called = True
            return {}

        monkeypatch.setattr(bank_import, "suggest_categories_ai", fake_ai)
        content = kbc_csv(
            [
                kbc_row(
                    bedrag="-1000,00",
                    omschrijving="INSTANTOVERSCHRIJVING NAAR SPAARREKENING",
                    tegenpartij_rek="BE55 6666 7777 8888",
                    vrij="Tv",
                )
            ]
        )
        (row,) = build_preview(import_db, "kbc.csv", content, _settings()).rows
        assert row.is_internal_transfer
        assert row.suggestion_source is None
        assert called is False  # geen openstaande rijen → geen AI-call


# ── Laag 3: AI (gemockte client) ─────────────────────────────────────────────


class TestSuggestCategoriesAi:
    def _cats(self, db: Session) -> list[Category]:
        return [_cat(db, "Boodschappen"), _cat(db, "Cadeaus")]

    def test_mapt_index_naar_categorie(
        self, import_db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cats = self._cats(import_db)
        _mock_client(monkeypatch, reply=json.dumps({"0": "Boodschappen", "1": "Cadeaus"}))
        candidates = [
            TxCandidate("Winkel A", None, "x", -500),
            TxCandidate("Winkel B", None, "y", -600),
        ]
        result = suggest_categories_ai(
            candidates,
            cats,
            _settings(anthropic_api_key="x", import_ai_categorization_enabled=True),
        )
        assert result == {0: cats[0].id, 1: cats[1].id}

    def test_uitgeschakeld_doet_geen_call(
        self, import_db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(settings):
            raise AssertionError("client mag niet aangemaakt worden als de laag uit staat")

        monkeypatch.setattr(import_categorization, "_client", boom)
        result = suggest_categories_ai(
            [TxCandidate("A", None, "x", -1)],
            self._cats(import_db),
            _settings(anthropic_api_key="x", import_ai_categorization_enabled=False),
        )
        assert result == {}

    def test_zonder_key_geen_call(self, import_db: Session) -> None:
        # Echte _client (geen mock): lege key → None → lege dict, geen netwerk.
        result = suggest_categories_ai(
            [TxCandidate("A", None, "x", -1)],
            self._cats(import_db),
            _settings(anthropic_api_key="", import_ai_categorization_enabled=True),
        )
        assert result == {}

    def test_ai_fout_is_niet_fataal(
        self, import_db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mock_client(monkeypatch, error=anthropic.APIConnectionError(request=SimpleNamespace()))
        result = suggest_categories_ai(
            [TxCandidate("A", None, "x", -1)],
            self._cats(import_db),
            _settings(anthropic_api_key="x", import_ai_categorization_enabled=True),
        )
        assert result == {}

    def test_ongeldig_antwoord_is_niet_fataal(
        self, import_db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mock_client(monkeypatch, reply="dit is geen JSON")
        result = suggest_categories_ai(
            [TxCandidate("A", None, "x", -1)],
            self._cats(import_db),
            _settings(anthropic_api_key="x", import_ai_categorization_enabled=True),
        )
        assert result == {}

    def test_onbekende_categorienaam_genegeerd(
        self, import_db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mock_client(monkeypatch, reply=json.dumps({"0": "Onbestaande categorie"}))
        result = suggest_categories_ai(
            [TxCandidate("A", None, "x", -1)],
            self._cats(import_db),
            _settings(anthropic_api_key="x", import_ai_categorization_enabled=True),
        )
        assert result == {}

    def test_index_buiten_bereik_genegeerd(
        self, import_db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cats = self._cats(import_db)
        _mock_client(monkeypatch, reply=json.dumps({"0": "Boodschappen", "5": "Cadeaus"}))
        result = suggest_categories_ai(
            [TxCandidate("A", None, "x", -1)],
            cats,
            _settings(anthropic_api_key="x", import_ai_categorization_enabled=True),
        )
        assert result == {0: cats[0].id}

    def test_zonder_kandidaten_of_categorieen(self, import_db: Session) -> None:
        settings = _settings(anthropic_api_key="x", import_ai_categorization_enabled=True)
        assert suggest_categories_ai([], self._cats(import_db), settings) == {}
        assert suggest_categories_ai([TxCandidate("A", None, "x", -1)], [], settings) == {}
