"""CSV-parsers voor de KBC- en BNP Paribas Fortis-exports (spec §5.2).

Pure functies, geen database. Bedragen komen als tekst met decimale komma en
worden exact als Decimal geparst (nooit float). De parser levert getekende
bedragen zoals de bank ze rapporteert; de tekenconventie van de app (+ =
Inkomen, − = Uitgaven/Sparen) valt daar vanzelf mee samen.

Formaat-quirks (geverifieerd tegen echte exports, 05/07/2026):
- Fortis: UTF-8 mét BOM, ';', datum dd/mm/jjjj, rijen met Status ≠
  "Geaccepteerd" overslaan. Bij kaartbetalingen zijn de tegenpartijkolommen
  leeg en zit de handelaar in de Details-tekst.
- KBC: ';', rijen gescheiden door \r zónder \n, zware padding-spaties in alle
  velden, tegenpartij-IBAN mét spaties. Bij Bancontact-betalingen en
  domiciliëringen zit de handelaar/schuldeiser alleen in de Omschrijving.

De import_hash is het dedupe-contract (spec §5.2): Fortis op
(rekeningnummer, volgnummer), KBC op (rekeningnummer, afschriftnummer, datum,
bedrag, omschrijving). Wijzig dit nooit zonder migratiepad — bestaande
transacties zouden anders opnieuw geïmporteerd worden.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.models.enums import Bank

_FORTIS_HEADER_PREFIX = "Volgnummer;Uitvoeringsdatum"
_KBC_HEADER_PREFIX = "Rekeningnummer;Rubrieknaam"
_FORTIS_COLUMNS = 13
_KBC_COLUMNS = 18
_FORTIS_STATUS_OK = "Geaccepteerd"

# Merchant-extractie is best-effort en enkel voor counterparty_name (weergave
# en regels op tegenpartijnaam); categorisatie werkt ook zonder via description.
_FORTIS_MERCHANT_RE = re.compile(r"NUMMER \d{4} \d{2}XX XXXX \d{4}\s+(.+?)\s+\d{2}/\d{2}/\d{4}")
_KBC_MERCHANT_RE = re.compile(r"OM \d{2}\.\d{2} UUR(?: \d+)?\s+(.+?)\s+MET KBC-DEBETKAART")
_KBC_SCHULDEISER_RE = re.compile(r"SCHULDEISER\s*:\s*(.+?)\s+(?:REF\.|MANDAATREFERTE|MEDEDELING)")
_KBC_PLAATS_SUFFIX_RE = re.compile(r"\s+BE\d{4}\s+\S+$")
_IBAN_IN_TEKST_RE = re.compile(r"\b[A-Z]{2}\d{2}(?: ?\d{4}){3}(?: ?\d{1,4})?\b")


class UnknownFormatError(ValueError):
    """De upload matcht geen van de gekende bankformaten."""


@dataclass(frozen=True)
class ParsedRow:
    date: date
    amount: Decimal  # getekend: + = credit, − = debet
    account_iban: str  # genormaliseerd (spaties weg, uppercase)
    counterparty_iban: str | None
    counterparty_name: str | None
    description: str | None
    import_hash: str


@dataclass
class ParseResult:
    bank: Bank
    rows: list[ParsedRow] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def normalize_iban(value: str) -> str:
    return "".join(value.split()).upper()


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def _hash(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%d/%m/%Y").date()


def _parse_amount(raw: str) -> Decimal:
    """Decimale komma (en eventueel punt als duizendtal) → exacte Decimal."""
    return Decimal(raw.replace(".", "").replace(",", "."))


def detect_bank(content: bytes) -> Bank | None:
    text = _decode(content).lstrip()
    if text.startswith(_FORTIS_HEADER_PREFIX):
        return Bank.FORTIS
    if text.startswith(_KBC_HEADER_PREFIX):
        return Bank.KBC
    return None


def parse_bank_csv(content: bytes) -> ParseResult:
    bank = detect_bank(content)
    if bank == Bank.FORTIS:
        return parse_fortis(content)
    if bank == Bank.KBC:
        return parse_kbc(content)
    raise UnknownFormatError("Geen KBC- of Fortis-export herkend aan de kolomkoppen")


def _extract_fortis_merchant(details: str) -> str | None:
    match = _FORTIS_MERCHANT_RE.search(details)
    return match.group(1) if match else None


def _extract_kbc_counterparty_name(omschrijving: str) -> str | None:
    match = _KBC_MERCHANT_RE.search(omschrijving)
    if match:
        # Plaatsaanduiding ("BE9040 SINT-AMANDSBE") achter de handelaar weglaten
        return _KBC_PLAATS_SUFFIX_RE.sub("", match.group(1))
    match = _KBC_SCHULDEISER_RE.search(omschrijving)
    return match.group(1) if match else None


def parse_fortis(content: bytes) -> ParseResult:
    result = ParseResult(bank=Bank.FORTIS)
    reader = csv.reader(io.StringIO(_decode(content)), delimiter=";")
    next(reader, None)  # header
    for line_no, raw in enumerate(reader, start=2):
        if not any(cell.strip() for cell in raw):
            continue
        if len(raw) < _FORTIS_COLUMNS:
            result.skipped.append(f"rij {line_no}: {len(raw)} kolommen i.p.v. {_FORTIS_COLUMNS}")
            continue
        cells = [cell.strip() for cell in raw]
        volgnummer, uitvoeringsdatum, _, bedrag, _, rekening = cells[0:6]
        tegenpartij, naam, mededeling, details, status = cells[7:12]
        if status != _FORTIS_STATUS_OK:
            result.skipped.append(f"rij {line_no}: status '{status}'")
            continue
        try:
            tx_date = _parse_date(uitvoeringsdatum)
            amount = _parse_amount(bedrag)
        except (ValueError, InvalidOperation) as exc:
            result.skipped.append(f"rij {line_no}: {exc}")
            continue
        account_iban = normalize_iban(rekening)
        result.rows.append(
            ParsedRow(
                date=tx_date,
                amount=amount,
                account_iban=account_iban,
                counterparty_iban=normalize_iban(tegenpartij) or None,
                counterparty_name=naam or _extract_fortis_merchant(details),
                description=mededeling or details or None,
                import_hash=_hash("fortis", account_iban, volgnummer),
            )
        )
    return result


def parse_kbc(content: bytes) -> ParseResult:
    result = ParseResult(bank=Bank.KBC)
    # splitlines() splitst ook op een losse \r — de rijscheiding van de KBC-export
    reader = csv.reader(_decode(content).splitlines(), delimiter=";")
    next(reader, None)  # header
    for line_no, raw in enumerate(reader, start=2):
        if not any(cell.strip() for cell in raw):
            continue
        if len(raw) < _KBC_COLUMNS:
            result.skipped.append(f"rij {line_no}: {len(raw)} kolommen i.p.v. {_KBC_COLUMNS}")
            continue
        cells = [cell.strip() for cell in raw]
        rekening, _, _, _, afschrift, datum, omschrijving = cells[0:7]
        bedrag = cells[8]
        tegenpartij_rek, _, tegenpartij_naam = cells[12:15]
        vrij = cells[17]
        try:
            tx_date = _parse_date(datum)
            amount = _parse_amount(bedrag)
        except (ValueError, InvalidOperation) as exc:
            result.skipped.append(f"rij {line_no}: {exc}")
            continue
        counterparty_iban = normalize_iban(tegenpartij_rek) or None
        if counterparty_iban is None:
            # Bv. "AUTOMATISCH SPAREN … NAAR BE55 6666 7777 8888": IBAN zit in de tekst
            iban_match = _IBAN_IN_TEKST_RE.search(omschrijving)
            if iban_match:
                counterparty_iban = normalize_iban(iban_match.group(0))
        account_iban = normalize_iban(rekening)
        result.rows.append(
            ParsedRow(
                date=tx_date,
                amount=amount,
                account_iban=account_iban,
                counterparty_iban=counterparty_iban,
                counterparty_name=tegenpartij_naam or _extract_kbc_counterparty_name(omschrijving),
                description=vrij or omschrijving or None,
                import_hash=_hash("kbc", account_iban, afschrift, datum, bedrag, omschrijving),
            )
        )
    return result
