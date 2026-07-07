"""Rekeningbeheer per context (spec §6): toevoegen, hernoemen, (soft-)verwijderen.

Rekeningen zijn per context. "Verwijderen" = deactiveren (`active=False`) zodat de
maandstand-historiek (AccountSnapshot) intact blijft en de rekening uit de invoer
verdwijnt. Patroon van de categorie-service.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account
from app.models.enums import AccountType, Bank


class EmptyAccountNameError(ValueError):
    """De rekeningnaam is leeg."""


class DuplicateAccountError(ValueError):
    """Er bestaat al een actieve rekening met dezelfde naam in de context."""


def create_account(
    db: Session,
    context_id: int,
    name: str,
    type_: AccountType,
    bank: Bank,
    iban: str | None,
) -> Account:
    clean = name.strip()
    if not clean:
        raise EmptyAccountNameError("Rekeningnaam is leeg")

    existing = db.scalars(
        select(Account).where(Account.context_id == context_id, Account.name == clean)
    ).one_or_none()
    if existing is not None:
        if existing.active:
            raise DuplicateAccountError(f"Rekening '{clean}' bestaat al")
        existing.active = True  # reactiveren i.p.v. botsen met UniqueConstraint
        existing.type = type_
        existing.bank = bank
        existing.iban = iban or None
        db.commit()
        return existing

    account = Account(
        context_id=context_id, name=clean, type=type_, bank=bank, iban=iban or None, active=True
    )
    db.add(account)
    db.commit()
    return account


def update_account(
    db: Session, account: Account, name: str, type_: AccountType, bank: Bank, iban: str | None
) -> Account:
    clean = name.strip()
    if not clean:
        raise EmptyAccountNameError("Rekeningnaam is leeg")
    account.name = clean
    account.type = type_
    account.bank = bank
    account.iban = iban or None
    db.commit()
    return account


def deactivate_account(db: Session, account: Account) -> None:
    account.active = False
    db.commit()
