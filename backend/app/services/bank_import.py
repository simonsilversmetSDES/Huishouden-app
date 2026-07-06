"""Orchestratie van de CSV-import (spec §5.2–5.3): preview zonder DB-writes.

Twee fasen, stateless:
1. build_preview: parse → rekening-resolutie (Rekeningnummer ↔ accounts.iban)
   → dedupe-check op import_hash → regelengine → interne-overschrijvings-
   detectie → typesuggestie. Schrijft niets weg.
2. commit_import (aparte stap): de bevestigde rijen opslaan, met hervalidatie.

Interne overschrijvingen (afspraak 06/07/2026): enkel tegenpartij-IBAN's van
rekeningen binnen dezelfde context tellen als intern — de bijdrage van een
persoonlijke rekening naar de gemeenschappelijke is budgetinkomen, geen
interne overschrijving. Een regelmatch op een Sparen-categorie (bv.
AUTOMATISCH SPAREN) wint van de interne vlag: sparen telt als budget-actual.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, Context, Transaction
from app.models.enums import CategoryType
from app.schemas.imports import AccountRef, ImportPreviewOut, PreviewRowOut
from app.services.budget import to_cents
from app.services.csv_parsers import ParsedRow, normalize_iban, parse_bank_csv
from app.services.rules import MatchCandidate, load_rules, match_rule


class MultipleAccountsError(ValueError):
    """Het bestand bevat rijen van meer dan één rekening (v1: niet ondersteund)."""


def _sign_type(row: ParsedRow) -> CategoryType:
    return CategoryType.INKOMEN if row.amount > 0 else CategoryType.UITGAVEN


def _resolve_account(db: Session, rows: list[ParsedRow]) -> tuple[Account | None, list[str]]:
    file_ibans = sorted({row.account_iban for row in rows})
    if len(file_ibans) > 1:
        raise MultipleAccountsError(
            f"Bestand bevat meerdere rekeningnummers: {', '.join(file_ibans)}"
        )
    if not file_ibans:
        return None, []
    by_iban = {
        normalize_iban(account.iban): account
        for account in db.scalars(select(Account).where(Account.iban.is_not(None)))
        if account.iban
    }
    account = by_iban.get(file_ibans[0])
    return account, [] if account else file_ibans


def _known_hashes(db: Session) -> set[str]:
    return set(
        db.scalars(select(Transaction.import_hash).where(Transaction.import_hash.is_not(None)))
    )


def build_preview(db: Session, filename: str, content: bytes) -> ImportPreviewOut:
    parsed = parse_bank_csv(content)  # UnknownFormatError propageert naar de route
    account, unmatched = _resolve_account(db, parsed.rows)

    rules = []
    categories: dict[int, Category] = {}
    own_context_ibans: set[str] = set()
    account_ref = None
    if account is not None:
        context = db.get(Context, account.context_id)
        assert context is not None
        account_ref = AccountRef(
            id=account.id, name=account.name, context_id=context.id, context_name=context.name
        )
        rules = load_rules(db, context.id)
        categories = {
            category.id: category
            for category in db.scalars(select(Category).where(Category.context_id == context.id))
        }
        own_context_ibans = {
            normalize_iban(a.iban)
            for a in db.scalars(
                select(Account).where(Account.context_id == context.id, Account.iban.is_not(None))
            )
            if a.iban
        }

    known = _known_hashes(db)
    seen_in_file: set[str] = set()
    rows: list[PreviewRowOut] = []
    for row in parsed.rows:
        duplicate = row.import_hash in known or row.import_hash in seen_in_file
        seen_in_file.add(row.import_hash)

        rule = match_rule(
            rules,
            MatchCandidate(
                counterparty_name=row.counterparty_name,
                counterparty_iban=row.counterparty_iban,
                description=row.description,
            ),
        )
        category = categories[rule.category_id] if rule else None
        is_internal = (
            row.counterparty_iban is not None
            and row.counterparty_iban in own_context_ibans
            and not (category and category.type == CategoryType.SPAREN)
        )
        if is_internal:
            category, rule = None, None
        rows.append(
            PreviewRowOut(
                date=row.date,
                effective_date=row.date,
                amount_cents=to_cents(row.amount),
                type=category.type if category else _sign_type(row),
                counterparty_name=row.counterparty_name,
                counterparty_iban=row.counterparty_iban,
                description=row.description,
                import_hash=row.import_hash,
                duplicate=duplicate,
                is_internal_transfer=is_internal,
                suggested_category_id=category.id if category else None,
                suggested_category_name=category.name if category else None,
                matched_rule_id=rule.id if rule else None,
            )
        )

    duplicate_count = sum(1 for r in rows if r.duplicate)
    return ImportPreviewOut(
        bank=parsed.bank,
        filename=filename,
        account=account_ref,
        unmatched_ibans=unmatched,
        rows=rows,
        new_count=len(rows) - duplicate_count,
        duplicate_count=duplicate_count,
        uncategorized_count=sum(
            1
            for r in rows
            if not r.duplicate and not r.is_internal_transfer and r.suggested_category_id is None
        ),
        skipped=parsed.skipped,
    )
