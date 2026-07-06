"""Tests voor de importflow (spec §5.2): preview met rekeningmatch, dedupe,
regelsuggesties en interne-overschrijvingsdetectie.

Interne overschrijvingen: enkel binnen dezelfde context; een Sparen-regelmatch
(AUTOMATISCH SPAREN) wint van de vlag; de cross-context "Gemeenschappelijke
bijdrage" blijft gewoon inkomen.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Transaction
from app.models.enums import Bank, Categorization, CategoryType
from app.seed import seed_accounts, seed_contexts, seed_rules
from app.services.bank_import import MultipleAccountsError, build_preview
from tests.csv_fixtures import (
    FORTIS_ACCOUNT,
    KBC_ACCOUNT,
    fortis_csv,
    fortis_row,
    kbc_card_row,
    kbc_csv,
    kbc_row,
)

KBC_SPAAR = "BE55666677778888"
FORTIS_SPAAR = "BE77888899990000"
JOZEFIEN_ZICHT = "BE11222233334444"


@pytest.fixture
def import_db(seeded_db: Session) -> Session:
    """seeded_db + rekeningen mét IBAN's en de seed-regels."""
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


class TestBuildPreview:
    def test_rekeningmatch_en_regelsuggestie(self, import_db: Session) -> None:
        content = kbc_csv([kbc_card_row(merchant="3815 COLRUYT SINT-AMAN", bedrag="-9,66")])
        preview = build_preview(import_db, "kbc.csv", content)

        assert preview.bank == Bank.KBC
        assert preview.account is not None
        assert preview.account.context_name == "Gemeenschappelijk"
        assert preview.unmatched_ibans == []
        (row,) = preview.rows
        assert row.amount_cents == -966
        assert row.type == CategoryType.UITGAVEN
        assert row.effective_date == row.date
        assert row.suggested_category_name == "Boodschappen"
        assert row.matched_rule_id is not None
        assert not row.duplicate
        assert preview.new_count == 1
        assert preview.uncategorized_count == 0

    def test_positief_zonder_regel_wordt_inkomen(self, import_db: Session) -> None:
        content = kbc_csv(
            [
                kbc_row(
                    bedrag="42,72",
                    omschrijving="OVERSCHRIJVING VAN ONBEKENDE NV",
                    tegenpartij_naam="ONBEKENDE NV",
                )
            ]
        )
        (row,) = build_preview(import_db, "kbc.csv", content).rows
        assert row.type == CategoryType.INKOMEN
        assert row.suggested_category_id is None

    def test_duplicaat_in_database(self, import_db: Session) -> None:
        content = kbc_csv([kbc_card_row(merchant="CINAIR", bedrag="-16,00")])
        eerste = build_preview(import_db, "kbc.csv", content).rows[0]
        import_db.add(
            Transaction(
                context_id=1,
                date=date(2026, 6, 26),
                amount=Decimal("-16.00"),
                type=CategoryType.UITGAVEN,
                import_hash=eerste.import_hash,
                categorization=Categorization.AUTO,
            )
        )
        import_db.commit()

        preview = build_preview(import_db, "kbc.csv", content)
        assert preview.rows[0].duplicate
        assert preview.new_count == 0
        assert preview.duplicate_count == 1

    def test_duplicaat_binnen_bestand(self, import_db: Session) -> None:
        rij = kbc_card_row(merchant="CINAIR", bedrag="-9,50")
        preview = build_preview(import_db, "kbc.csv", kbc_csv([rij, rij]))
        assert [r.duplicate for r in preview.rows] == [False, True]

    def test_geen_rekeningmatch(self, import_db: Session) -> None:
        content = kbc_csv([kbc_row(rekening="BE00999988887777")])
        preview = build_preview(import_db, "kbc.csv", content)
        assert preview.account is None
        assert preview.unmatched_ibans == ["BE00999988887777"]
        # Rijen blijven zichtbaar, maar zonder suggesties
        assert len(preview.rows) == 1
        assert preview.rows[0].suggested_category_id is None

    def test_meerdere_rekeningen_geeft_fout(self, import_db: Session) -> None:
        content = kbc_csv([kbc_row(rekening=KBC_ACCOUNT), kbc_row(rekening="BE00999988887777")])
        with pytest.raises(MultipleAccountsError):
            build_preview(import_db, "kbc.csv", content)

    def test_interne_overschrijving_zelfde_context(self, import_db: Session) -> None:
        """KBC zicht → KBC spaar (zelfde context): geflagd, geen categorie."""
        content = kbc_csv(
            [
                kbc_row(
                    bedrag="-1000,00",
                    omschrijving="INSTANTOVERSCHRIJVING NAAR SPAARREKENING",
                    tegenpartij_rek="BE55 6666 7777 8888",
                    tegenpartij_naam="EIGEN SPAARREKENING",
                    vrij="Tv",
                )
            ]
        )
        (row,) = build_preview(import_db, "kbc.csv", content).rows
        assert row.is_internal_transfer
        assert row.suggested_category_id is None
        assert row.type == CategoryType.UITGAVEN  # teken; wordt uitgesloten van budget

    def test_bijdrage_cross_context_niet_intern(self, import_db: Session) -> None:
        """Fortis Simon → gemeenschappelijke KBC: géén interne overschrijving."""
        content = fortis_csv(
            [
                fortis_row(
                    bedrag="-1600,00",
                    tegenpartij=KBC_ACCOUNT,
                    naam="gemeenschappelijke rekening",
                    mededeling="Gemeenschappelijke bijdrage",
                )
            ]
        )
        preview = build_preview(import_db, "fortis.csv", content)
        assert preview.account is not None
        assert preview.account.context_name == "Simon"
        (row,) = preview.rows
        assert not row.is_internal_transfer

    def test_sparen_regel_wint_van_interne_vlag(self, import_db: Session) -> None:
        """AUTOMATISCH SPAREN naar eigen spaarrekening telt als budget-Sparen."""
        content = kbc_csv(
            [
                kbc_row(
                    bedrag="-100,00",
                    omschrijving="AUTOMATISCH SPAREN                   02-06 "
                    "NAAR BE55 6666 7777 8888 SPAARACTIE",
                )
            ]
        )
        (row,) = build_preview(import_db, "kbc.csv", content).rows
        assert not row.is_internal_transfer
        assert row.suggested_category_name == "Spaarrekening"
        assert row.type == CategoryType.SPAREN

    def test_loon_regel_in_context_simon(self, import_db: Session) -> None:
        content = fortis_csv(
            [
                fortis_row(
                    bedrag="5162,06",
                    naam="WERKGEVER NV",
                    mededeling="/A/ LOON PERIODE 01.06.2026-30.06.2026 / VERLOFGELD",
                )
            ]
        )
        (row,) = build_preview(import_db, "fortis.csv", content).rows
        assert row.suggested_category_name == "Loon"
        assert row.type == CategoryType.INKOMEN


class TestPreviewApi:
    def test_preview_endpoint(self, import_db: Session, logged_in) -> None:
        content = kbc_csv([kbc_card_row(merchant="JUST RUSSEL", bedrag="-29,95")])
        resp = logged_in.post(
            "/api/imports/preview", files={"file": ("kbc.csv", content, "text/csv")}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["bank"] == "KBC"
        assert data["account"]["context_name"] == "Gemeenschappelijk"
        assert data["rows"][0]["suggested_category_name"] == "Katten"
        assert data["rows"][0]["amount_cents"] == -2995

    def test_preview_onbekend_formaat(self, import_db: Session, logged_in) -> None:
        resp = logged_in.post(
            "/api/imports/preview", files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")}
        )
        assert resp.status_code == 422

    def test_preview_vereist_login(self, client) -> None:
        resp = client.post("/api/imports/preview", files={"file": ("x.csv", b"a;b", "text/csv")})
        assert resp.status_code == 401
