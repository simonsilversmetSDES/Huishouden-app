"""Parser-tests voor de KBC- en Fortis-CSV-formaten (spec §5.2, tests-first).

De fixtures repliceren de quirks van de echte exports: Fortis met UTF-8-BOM en
statusfilter, KBC met \r-rijscheiding en padding-spaties. De import_hash is een
contract (dedupe over imports heen) en wordt hier expliciet vastgelegd.
"""

from datetime import date
from decimal import Decimal
from hashlib import sha256

import pytest

from app.models.enums import Bank
from app.services.csv_parsers import (
    UnknownFormatError,
    detect_bank,
    normalize_iban,
    parse_bank_csv,
    parse_fortis,
    parse_kbc,
)
from tests.csv_fixtures import (
    FORTIS_ACCOUNT,
    KBC_ACCOUNT,
    fortis_card_row,
    fortis_csv,
    fortis_row,
    kbc_card_row,
    kbc_csv,
    kbc_domiciliering_row,
    kbc_row,
)


def _hash(*parts: str) -> str:
    return sha256(":".join(parts).encode("utf-8")).hexdigest()


class TestNormalizeIban:
    def test_spaties_en_kleine_letters(self) -> None:
        assert normalize_iban("be11 2222 3333 4444") == "BE11222233334444"

    def test_al_genormaliseerd(self) -> None:
        assert normalize_iban(FORTIS_ACCOUNT) == FORTIS_ACCOUNT


class TestDetectBank:
    def test_fortis_met_bom(self) -> None:
        assert detect_bank(fortis_csv([fortis_row()])) == Bank.FORTIS

    def test_fortis_zonder_bom(self) -> None:
        assert detect_bank(fortis_csv([fortis_row()], bom=False)) == Bank.FORTIS

    def test_kbc(self) -> None:
        assert detect_bank(kbc_csv([kbc_row()])) == Bank.KBC

    def test_onbekend_formaat(self) -> None:
        assert detect_bank(b"kolom1,kolom2\n1,2\n") is None

    def test_parse_bank_csv_onbekend_geeft_fout(self) -> None:
        with pytest.raises(UnknownFormatError):
            parse_bank_csv(b"kolom1,kolom2\n1,2\n")

    def test_parse_bank_csv_dispatch(self) -> None:
        assert parse_bank_csv(fortis_csv([fortis_row()])).bank == Bank.FORTIS
        assert parse_bank_csv(kbc_csv([kbc_row()])).bank == Bank.KBC


class TestParseFortis:
    def test_basisvelden(self) -> None:
        content = fortis_csv(
            [
                fortis_row(
                    volgnummer="2026-00186",
                    datum="29/06/2026",
                    bedrag="5162,06",
                    tegenpartij="BE20914001278412",
                    naam="WERKGEVER NV",
                    mededeling="/A/ LOON PERIODE 01.06.2026-30.06.2026",
                )
            ]
        )
        result = parse_fortis(content)
        assert result.bank == Bank.FORTIS
        assert result.skipped == []
        (row,) = result.rows
        assert row.date == date(2026, 6, 29)
        assert row.amount == Decimal("5162.06")
        assert row.account_iban == FORTIS_ACCOUNT
        assert row.counterparty_iban == "BE20914001278412"
        assert row.counterparty_name == "WERKGEVER NV"
        assert row.description == "/A/ LOON PERIODE 01.06.2026-30.06.2026"

    def test_negatief_bedrag_met_komma(self) -> None:
        (row,) = parse_fortis(fortis_csv([fortis_row(bedrag="-731,57")])).rows
        assert row.amount == Decimal("-731.57")

    def test_status_niet_geaccepteerd_wordt_overgeslagen(self) -> None:
        content = fortis_csv(
            [
                fortis_row(volgnummer="2026-00001"),
                fortis_row(volgnummer="2026-00002", status="Geweigerd", reden="saldo"),
            ]
        )
        result = parse_fortis(content)
        assert len(result.rows) == 1
        assert len(result.skipped) == 1
        assert "Geweigerd" in result.skipped[0]

    def test_kaartbetaling_merchant_uit_details(self) -> None:
        content = fortis_csv([fortis_card_row(merchant="BAKKERIJ DE MIK EKE")])
        (row,) = parse_fortis(content).rows
        assert row.counterparty_iban is None
        assert row.counterparty_name == "BAKKERIJ DE MIK EKE"
        # Mededeling leeg → description valt terug op Details
        assert row.description is not None
        assert "BETALING MET DEBETKAART" in row.description

    def test_description_fallback_op_details(self) -> None:
        (row,) = parse_fortis(fortis_csv([fortis_row(mededeling="", details="DETAILTEKST")])).rows
        assert row.description == "DETAILTEKST"

    def test_import_hash_contract(self) -> None:
        """Hash = sha256('fortis:<rekening>:<volgnummer>') — dedupe-sleutel uit de spec."""
        (row,) = parse_fortis(fortis_csv([fortis_row(volgnummer="2026-00186")])).rows
        assert row.import_hash == _hash("fortis", FORTIS_ACCOUNT, "2026-00186")

    def test_import_hash_stabiel_en_uniek(self) -> None:
        rij = fortis_row(volgnummer="2026-00010")
        eerste = parse_fortis(fortis_csv([rij])).rows[0].import_hash
        tweede = parse_fortis(fortis_csv([rij])).rows[0].import_hash
        ander = parse_fortis(fortis_csv([fortis_row(volgnummer="2026-00011")])).rows[0].import_hash
        assert eerste == tweede
        assert eerste != ander

    def test_onvolledige_rij_geeft_skip_met_reden(self) -> None:
        content = fortis_csv(["2026-00001;29/06/2026;onvolledig"])
        result = parse_fortis(content)
        assert result.rows == []
        assert len(result.skipped) == 1


class TestParseKbc:
    def test_rijen_gescheiden_door_cr_zonder_lf(self) -> None:
        content = kbc_csv([kbc_row(afschrift="02026001"), kbc_row(afschrift="02026002")])
        assert b"\n" not in content
        result = parse_kbc(content)
        assert len(result.rows) == 2
        assert result.skipped == []

    def test_padding_wordt_getrimd_en_basisvelden(self) -> None:
        content = kbc_csv(
            [
                kbc_row(
                    datum="30/06/2026",
                    bedrag="1500,00",
                    omschrijving="INSTANTOVERSCHRIJVING VAN            30-06 TESTPARTIJ",
                    tegenpartij_rek="BE11 2222 3333 4444",
                    tegenpartij_naam="PARTNER PETRA",
                    vrij="Bijdrage loon juni",
                )
            ]
        )
        (row,) = parse_kbc(content).rows
        assert row.date == date(2026, 6, 30)
        assert row.amount == Decimal("1500.00")
        assert row.account_iban == KBC_ACCOUNT
        assert row.counterparty_iban == "BE11222233334444"  # spaties genormaliseerd
        assert row.counterparty_name == "PARTNER PETRA"  # padding weg
        assert row.description == "Bijdrage loon juni"

    def test_description_fallback_op_omschrijving(self) -> None:
        (row,) = parse_kbc(
            kbc_csv([kbc_row(omschrijving="AUTOMATISCH SPAREN 02-06", vrij="")])
        ).rows
        assert row.description == "AUTOMATISCH SPAREN 02-06"

    def test_bancontact_merchant_uit_omschrijving(self) -> None:
        (row,) = parse_kbc(
            kbc_csv([kbc_card_row(merchant="SPEELGOEDWINKEL NOORD", plaats="BE9070 DESTELBERGEN")])
        ).rows
        assert row.counterparty_iban is None
        assert row.counterparty_name == "SPEELGOEDWINKEL NOORD"

    def test_bancontact_merchant_met_winkelnummer(self) -> None:
        """Echte export: 'OM 18.53 UUR 3815 COLRUYT SINT-AMAN BE9040 …'."""
        (row,) = parse_kbc(
            kbc_csv(
                [
                    kbc_card_row(
                        winkelnummer="3815",
                        merchant="SUPERMARKT WEST",
                        plaats="BE9040 SINT-AMANDSBE",
                    )
                ]
            )
        ).rows
        assert row.counterparty_name == "SUPERMARKT WEST"

    def test_domiciliering_schuldeiser_uit_omschrijving(self) -> None:
        (row,) = parse_kbc(kbc_csv([kbc_domiciliering_row(schuldeiser="MOBILE VIKINGS")])).rows
        assert row.counterparty_name == "MOBILE VIKINGS"
        assert row.counterparty_iban == "BE99000011112222"

    def test_automatisch_sparen_iban_uit_omschrijving(self) -> None:
        """Eigen spaar-IBAN staat alleen in de Omschrijving-tekst."""
        (row,) = parse_kbc(
            kbc_csv(
                [
                    kbc_row(
                        omschrijving="AUTOMATISCH SPAREN                   02-06 "
                        "NAAR BE55 6666 7777 8888 SPAARACTIE",
                        bedrag="-100,00",
                    )
                ]
            )
        ).rows
        assert row.counterparty_iban == "BE55666677778888"

    def test_import_hash_contract(self) -> None:
        """Hash = sha256('kbc:<rek>:<afschrift>:<datum>:<bedrag>:<omschrijving>')."""
        (row,) = parse_kbc(
            kbc_csv(
                [
                    kbc_row(
                        afschrift="02026133",
                        datum="30/06/2026",
                        bedrag="1500,00",
                        omschrijving="TESTOMSCHRIJVING",
                    )
                ]
            )
        ).rows
        assert row.import_hash == _hash(
            "kbc", KBC_ACCOUNT, "02026133", "30/06/2026", "1500,00", "TESTOMSCHRIJVING"
        )

    def test_import_hash_verschilt_per_afschrift(self) -> None:
        rows = parse_kbc(
            kbc_csv([kbc_row(afschrift="02026001"), kbc_row(afschrift="02026002")])
        ).rows
        assert rows[0].import_hash != rows[1].import_hash

    def test_ongeldige_datum_geeft_skip_met_reden(self) -> None:
        result = parse_kbc(kbc_csv([kbc_row(datum="geen datum")]))
        assert result.rows == []
        assert len(result.skipped) == 1
