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

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Account, CategorizationRule, Category, Context, Import, Transaction
from app.models.enums import Bank, Categorization, CategoryType, TransactionSource
from app.schemas.imports import (
    AccountRef,
    ImportCommitIn,
    ImportPreviewOut,
    ImportResultOut,
    PreviewRowOut,
)
from app.services.budget import from_cents, to_cents
from app.services.csv_parsers import ParsedRow, normalize_iban, parse_bank_csv
from app.services.rules import (
    MatchCandidate,
    build_category_resolver,
    load_rules,
    match_rule,
)
from app.services.transactions import UnknownCategoryError

_SOURCE_BY_BANK = {
    Bank.KBC: TransactionSource.IMPORT_KBC,
    Bank.FORTIS: TransactionSource.IMPORT_FORTIS,
}


class MultipleAccountsError(ValueError):
    """Het bestand bevat rijen van meer dan één rekening (v1: niet ondersteund)."""


class UnknownAccountError(ValueError):
    """De rekening bestaat niet of hoort niet bij de opgegeven context."""


class ConcurrentImportError(ValueError):
    """Zelfde bestand werd gelijktijdig gecommit (unique import_hash botste)."""


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

    rules: list[CategorizationRule] = []
    resolve_category = None
    own_context_ibans: set[str] = set()
    account_ref = None
    if account is not None:
        context = db.get(Context, account.context_id)
        assert context is not None
        account_ref = AccountRef(
            id=account.id, name=account.name, context_id=context.id, context_name=context.name
        )
        rules = load_rules(db, context.id)
        resolve_category = build_category_resolver(db, context.id, rules)
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
        category = resolve_category(rule) if (rule and resolve_category) else None
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


def commit_import(db: Session, body: ImportCommitIn) -> ImportResultOut:
    """Bevestigde rijen opslaan met hervalidatie en dedupe-hercheck.

    Idempotent: rijen waarvan de import_hash al bestaat worden geteld als
    duplicaat en overgeslagen — zelfde bestand twee keer committen = 0 nieuwe
    rijen. De UNIQUE-constraint op import_hash is de backstop tegen
    gelijktijdige commits (→ ConcurrentImportError).
    """
    account = db.get(Account, body.account_id)
    if account is None or account.context_id != body.context_id:
        raise UnknownAccountError("Onbekende rekening voor deze context")
    categories = {
        category.id: category
        for category in db.scalars(select(Category).where(Category.context_id == body.context_id))
    }
    for row in body.rows:
        if row.category_id is not None and row.category_id not in categories:
            raise UnknownCategoryError("Onbekende categorie voor deze context")

    known = _known_hashes(db)
    import_row = Import(filename=body.filename, bank=body.bank, imported_at=datetime.now())
    db.add(import_row)
    db.flush()

    created = duplicates = 0
    for row in body.rows:
        if row.import_hash in known:
            duplicates += 1
            continue
        known.add(row.import_hash)
        # Interne overschrijvingen blijven zonder categorie (uitgesloten van budget)
        category = None
        if not row.is_internal_transfer and row.category_id is not None:
            category = categories[row.category_id]
        if category is None:
            categorization = Categorization.UNCATEGORIZED
        elif row.categorization == Categorization.AUTO:
            categorization = Categorization.AUTO
        else:
            categorization = Categorization.MANUAL
        db.add(
            Transaction(
                context_id=body.context_id,
                account_id=account.id,
                category_id=category.id if category else None,
                date=row.date,
                effective_date=row.effective_date or row.date,
                amount=from_cents(row.amount_cents),
                type=category.type if category else row.type,
                counterparty_name=row.counterparty_name,
                counterparty_iban=row.counterparty_iban,
                description=row.description,
                source=_SOURCE_BY_BANK[body.bank],
                import_id=import_row.id,
                import_hash=row.import_hash,
                categorization=categorization,
                is_internal_transfer=row.is_internal_transfer,
            )
        )
        created += 1

    import_row.row_count = created
    import_row.duplicate_count = duplicates
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConcurrentImportError(
            "Import botste met een gelijktijdige import van hetzelfde bestand — probeer opnieuw"
        ) from exc
    return ImportResultOut(
        import_id=import_row.id, created_count=created, duplicate_count=duplicates
    )
