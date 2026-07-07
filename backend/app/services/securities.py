"""CRUD-helpers voor effecten en beleggingstransacties (spec §7).

Het transactietotaal wordt server-side berekend uit exacte Decimals:
- aankoop: totaal = aantal × prijs + kost + beurstaks (kostbasis);
- verkoop: totaal = aantal × prijs − kost − beurstaks (netto-opbrengst).
Alles Decimal (nooit float).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from app.models import SecurityTransaction
from app.models.enums import SecuritySide
from app.schemas.investments import SecurityTransactionIn

# Beurscode in de gemigreerde naam ("… (XETR:VWCE)") → yfinance-suffix.
_EXCHANGE_SUFFIX: dict[str, str] = {
    "XETR": ".DE",  # Xetra (Frankfurt)
    "XFRA": ".F",
    "XAMS": ".AS",  # Euronext Amsterdam
    "XBRU": ".BR",  # Euronext Brussel
    "XPAR": ".PA",  # Euronext Parijs
    "XLON": ".L",  # London
    "XMIL": ".MI",  # Milaan
    "XMAD": ".MC",  # Madrid
    "XSWX": ".SW",  # Zwitserland
    "XNAS": "",  # US: geen suffix
    "XNYS": "",
}
_PAREN_TICKER = re.compile(r"\(([A-Z0-9]+):([A-Za-z0-9.\-]+)\)")


def suggest_ticker(name: str) -> str | None:
    """Yfinance-ticker afleiden uit de effectnaam, of None als het niet lukt.

    "ALPHABET INC. (XETR:ABEA)" → "ABEA.DE"; "BTC/EUR" → "BTC-EUR". Onbekende
    beurs → None (gebruiker vult dan zelf in of zoekt via Yahoo).
    """
    match = _PAREN_TICKER.search(name)
    if match:
        exchange, symbol = match.group(1), match.group(2)
        suffix = _EXCHANGE_SUFFIX.get(exchange)
        return None if suffix is None else f"{symbol}{suffix}"
    if "/" in name:  # crypto-paar, bv. BTC/EUR
        return name.replace("/", "-")
    return None


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
