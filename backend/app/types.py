"""Custom SQLAlchemy-types voor geld en exacte hoeveelheden.

Harde regel (CLAUDE.md): geld nooit als float. Bedragen gaan als integer-centen
de database in; hoeveelheden/koersen met meer dan 2 decimalen als exacte tekst.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import Integer, String
from sqlalchemy.types import TypeDecorator

_CENT = Decimal("0.01")


def _to_decimal(value: Any, context: str) -> Decimal:
    if isinstance(value, float):
        raise TypeError(
            f"{context}: float is niet toegelaten voor geldwaarden — gebruik Decimal, int of str"
        )
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | str):
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"{context}: '{value}' is geen geldig getal") from exc
    raise TypeError(f"{context}: type {type(value).__name__} wordt niet ondersteund")


class MoneyCents(TypeDecorator[Decimal]):
    """Geldbedrag: Python Decimal (2 decimalen) <-> INTEGER centen in SQLite."""

    impl = Integer
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> int | None:
        if value is None:
            return None
        dec = _to_decimal(value, "MoneyCents")
        cents = dec * 100
        if cents != cents.to_integral_value():
            raise ValueError(
                f"MoneyCents: {dec} heeft meer dan 2 decimalen en is niet exact in centen"
            )
        return int(cents)

    def process_result_value(self, value: int | None, dialect: Any) -> Decimal | None:
        if value is None:
            return None
        return Decimal(value) * _CENT


class PreciseDecimal(TypeDecorator[Decimal]):
    """Exacte Decimal (aandelen-aantallen, koersen) <-> TEXT in SQLite."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return str(_to_decimal(value, "PreciseDecimal"))

    def process_result_value(self, value: str | None, dialect: Any) -> Decimal | None:
        if value is None:
            return None
        return Decimal(value)
