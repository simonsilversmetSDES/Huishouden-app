"""Enums uit spec §3. Opslag als tekst met CheckConstraint (geen native enum in SQLite)."""

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class Bank(StrEnum):
    KBC = "KBC"
    FORTIS = "Fortis"
    ANDERE = "Andere"


class AccountType(StrEnum):
    ZICHT = "zicht"
    SPAAR = "spaar"
    BELEGGING = "belegging"
    ANDERE = "andere"
    PENSIOENSPAREN = "pensioensparen"
    GROEPSVERZEKERING = "groepsverzekering"


class CategoryType(StrEnum):
    INKOMEN = "Inkomen"
    UITGAVEN = "Uitgaven"
    SPAREN = "Sparen"


class TransactionSource(StrEnum):
    MANUAL = "manual"
    IMPORT_KBC = "import_kbc"
    IMPORT_FORTIS = "import_fortis"
    IMPORT_EXCEL = "import_excel"  # eenmalige migratie uit het werkboek


class Categorization(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"
    UNCATEGORIZED = "uncategorized"


class MatchField(StrEnum):
    COUNTERPARTY_NAME = "counterparty_name"
    COUNTERPARTY_IBAN = "counterparty_iban"
    DESCRIPTION = "description"


class MatchType(StrEnum):
    CONTAINS = "contains"
    EQUALS = "equals"
    REGEX = "regex"


class SecuritySide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class AssetClass(StrEnum):
    CONTANT = "contant"
    ETF_FONDSEN = "etf_fondsen"
    PENSIOENSPAREN = "pensioensparen"
    GROEPSVERZEKERING = "groepsverzekering"
    WONING = "woning"
    AANDELEN = "aandelen"
    BITCOIN = "bitcoin"


class SecurityKind(StrEnum):
    """Soort belegging; de waarden vallen samen met de overeenkomstige AssetClass."""

    ETF_FONDSEN = "etf_fondsen"
    AANDELEN = "aandelen"
    BITCOIN = "bitcoin"


# Welke activaklasse in de vermogensbalans een rekening-type voedt (spec §6/§9).
ACCOUNT_TYPE_ASSET_CLASS: dict[AccountType, AssetClass] = {
    AccountType.ZICHT: AssetClass.CONTANT,
    AccountType.SPAAR: AssetClass.CONTANT,
    AccountType.BELEGGING: AssetClass.CONTANT,
    AccountType.ANDERE: AssetClass.CONTANT,
    AccountType.PENSIOENSPAREN: AssetClass.PENSIOENSPAREN,
    AccountType.GROEPSVERZEKERING: AssetClass.GROEPSVERZEKERING,
}


def str_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """Enum als VARCHAR + CheckConstraint, met de enum-values (niet de namen) als opslag."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        validate_strings=True,
        values_callable=lambda e: [m.value for m in e],
    )
