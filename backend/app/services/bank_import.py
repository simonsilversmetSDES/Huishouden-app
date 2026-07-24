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

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Account, CategorizationRule, Category, Context, Import, Transaction
from app.models.enums import Bank, Categorization, CategoryType, TransactionSource
from app.schemas.imports import (
    AccountRef,
    ImportCommitIn,
    ImportPreviewOut,
    ImportResultOut,
    PreviewRowOut,
    SuggestionSource,
)
from app.services.budget import from_cents, to_cents
from app.services.csv_parsers import ParsedRow, normalize_iban, parse_bank_csv
from app.services.import_categorization import (
    HistoryResolver,
    TxCandidate,
    build_history_resolver,
    suggest_categories_ai,
)
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


@dataclass
class _RowDraft:
    """Tussenstand per previewrij: eerst regel + historiek + interne-detectie, daarna
    (voor wat nog leeg is) de AI-fallback. Wordt op het eind naar een PreviewRowOut vertaald."""

    row: ParsedRow
    duplicate: bool
    is_internal: bool
    category: Category | None
    source: SuggestionSource | None
    rule: CategorizationRule | None


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


def build_preview(
    db: Session, filename: str, content: bytes, settings: Settings | None = None
) -> ImportPreviewOut:
    settings = settings or get_settings()
    parsed = parse_bank_csv(content)  # UnknownFormatError propageert naar de route
    account, unmatched = _resolve_account(db, parsed.rows)

    rules: list[CategorizationRule] = []
    resolve_category = None
    history: HistoryResolver | None = None
    active_categories: list[Category] = []
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
        history = build_history_resolver(db, context.id)
        active_categories = list(
            db.scalars(select(Category).where(Category.context_id == context.id, Category.active))
        )
        own_context_ibans = {
            normalize_iban(a.iban)
            for a in db.scalars(
                select(Account).where(Account.context_id == context.id, Account.iban.is_not(None))
            )
            if a.iban
        }

    known = _known_hashes(db)
    seen_in_file: set[str] = set()

    # Laag 1 (regel) + laag 2 (historiek) + interne-detectie, in één pass.
    drafts: list[_RowDraft] = []
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
        source: SuggestionSource | None = "rule" if category else None
        # Laag 2: enkel voor rijen die geen regelmatch kregen.
        if category is None and history is not None:
            category = history.resolve(
                TxCandidate(
                    counterparty_name=row.counterparty_name,
                    counterparty_iban=row.counterparty_iban,
                    description=row.description,
                    amount_cents=to_cents(row.amount),
                )
            )
            if category is not None:
                source = "history"

        is_internal = (
            row.counterparty_iban is not None
            and row.counterparty_iban in own_context_ibans
            and not (category and category.type == CategoryType.SPAREN)
        )
        if is_internal:
            category, rule, source = None, None, None
        drafts.append(_RowDraft(row, duplicate, is_internal, category, source, rule))

    # Laag 3 (AI): enkel nieuwe, niet-interne rijen die na regel + historiek nog leeg zijn.
    pending = [
        d for d in drafts if not d.duplicate and not d.is_internal and d.category is None
    ]
    if pending and active_categories:
        candidates = [
            TxCandidate(
                counterparty_name=d.row.counterparty_name,
                counterparty_iban=d.row.counterparty_iban,
                description=d.row.description,
                amount_cents=to_cents(d.row.amount),
            )
            for d in pending
        ]
        ai_result = suggest_categories_ai(
            candidates,
            active_categories,
            settings,
            examples=history.examples if history else None,
        )
        by_id = {c.id: c for c in active_categories}
        for index, category_id in ai_result.items():
            category = by_id.get(category_id)
            if category is not None:
                pending[index].category = category
                pending[index].source = "ai"

    rows = [
        PreviewRowOut(
            date=d.row.date,
            effective_date=d.row.date,
            amount_cents=to_cents(d.row.amount),
            type=d.category.type if d.category else _sign_type(d.row),
            counterparty_name=d.row.counterparty_name,
            counterparty_iban=d.row.counterparty_iban,
            description=d.row.description,
            import_hash=d.row.import_hash,
            duplicate=d.duplicate,
            is_internal_transfer=d.is_internal,
            suggested_category_id=d.category.id if d.category else None,
            suggested_category_name=d.category.name if d.category else None,
            suggestion_source=d.source,
            matched_rule_id=d.rule.id if d.rule else None,
        )
        for d in drafts
    ]

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
