"""CRUD-helpers voor effecten en beleggingstransacties (spec §7).

Het transactietotaal wordt server-side berekend uit exacte Decimals:
- aankoop: totaal = aantal × prijs + kost + beurstaks (kostbasis);
- verkoop: totaal = aantal × prijs − kost − beurstaks (netto-opbrengst).
Alles Decimal (nooit float).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.models import SecurityTransaction
from app.models.enums import SecuritySide
from app.schemas.investments import SecurityTransactionIn


class InvalidAmountError(ValueError):
    """Een hoeveelheid/koers/kost is geen geldig getal of buiten bereik."""


def _decimal(value: str, field: str, *, allow_zero: bool = True) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise InvalidAmountError(f"{field}: '{value}' is geen geldig getal") from exc
    if parsed < 0:
        raise InvalidAmountError(f"{field} mag niet negatief zijn")
    if not allow_zero and parsed == 0:
        raise InvalidAmountError(f"{field} mag niet 0 zijn")
    return parsed


def transaction_total(
    side: SecuritySide, shares: Decimal, price: Decimal, fee: Decimal, tax: Decimal
) -> Decimal:
    base = shares * price
    return base + fee + tax if side == SecuritySide.BUY else base - fee - tax


def apply_transaction(tx: SecurityTransaction, body: SecurityTransactionIn) -> None:
    shares = _decimal(body.shares, "Aantal", allow_zero=False)
    price = _decimal(body.price_per_share, "Prijs per stuk")
    fee = _decimal(body.fee, "Transactiekost")
    tax = _decimal(body.tax, "Beurstaks")
    tx.date = body.date
    tx.side = body.side
    tx.shares = shares
    tx.price_per_share = price
    tx.fee = fee
    tx.tax = tax
    tx.total = transaction_total(body.side, shares, price, fee, tax)
