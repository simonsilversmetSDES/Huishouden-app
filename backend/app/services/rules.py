"""Regelengine voor automatische categorisatie (spec §5.3).

Regels zijn per context en worden geëvalueerd op (priority ASC, id ASC),
first-match-wins. contains/equals matchen case-insensitive via casefold(),
regex met re.IGNORECASE. IBAN-regels matchen op genormaliseerd IBAN (spaties
weg, uppercase). Een None-veld matcht nooit; een ongeldige regex wordt bij het
matchen overgeslagen (en hoort bij CRUD geweigerd te worden).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CategorizationRule, Category, Transaction
from app.models.enums import Categorization, MatchField, MatchType
from app.services.csv_parsers import normalize_iban

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MatchCandidate:
    counterparty_name: str | None
    counterparty_iban: str | None
    description: str | None

    def value_for(self, field: MatchField) -> str | None:
        match field:
            case MatchField.COUNTERPARTY_NAME:
                return self.counterparty_name
            case MatchField.COUNTERPARTY_IBAN:
                return self.counterparty_iban
            case MatchField.DESCRIPTION:
                return self.description


def load_rules(db: Session, context_id: int) -> list[CategorizationRule]:
    return list(
        db.scalars(
            select(CategorizationRule)
            .where(CategorizationRule.context_id == context_id)
            .order_by(CategorizationRule.priority, CategorizationRule.id)
        )
    )


def _matches(match_type: MatchType, needle: str, value: str) -> bool:
    match match_type:
        case MatchType.CONTAINS:
            return needle.casefold() in value.casefold()
        case MatchType.EQUALS:
            return needle.casefold() == value.casefold()
        case MatchType.REGEX:
            try:
                return re.search(needle, value, re.IGNORECASE) is not None
            except re.error:
                logger.warning("Ongeldige regex in categorisatieregel: %r", needle)
                return False


def match_rule(
    rules: list[CategorizationRule], candidate: MatchCandidate
) -> CategorizationRule | None:
    """Eerste regel (in de meegegeven volgorde) die op de kandidaat matcht."""
    for rule in rules:
        value = candidate.value_for(rule.match_field)
        if not value:
            continue
        needle = rule.match_value
        if rule.match_field == MatchField.COUNTERPARTY_IBAN:
            value = normalize_iban(value)
            if rule.match_type != MatchType.REGEX:
                needle = normalize_iban(needle)
        if _matches(rule.match_type, needle, value):
            return rule
    return None


def apply_rules(db: Session, context_id: int, rule_id: int | None = None) -> int:
    """Regels retroactief toepassen op ongecategoriseerde transacties.

    Interne overschrijvingen en manueel/auto gecategoriseerde transacties
    blijven ongemoeid. Met rule_id wordt enkel die regel toegepast. De caller
    commit. Geeft het aantal bijgewerkte transacties terug.
    """
    rules = load_rules(db, context_id)
    if rule_id is not None:
        rules = [rule for rule in rules if rule.id == rule_id]
    if not rules:
        return 0
    categories = {
        category.id: category
        for category in db.scalars(select(Category).where(Category.context_id == context_id))
    }
    transactions = db.scalars(
        select(Transaction).where(
            Transaction.context_id == context_id,
            Transaction.categorization == Categorization.UNCATEGORIZED,
            Transaction.is_internal_transfer.is_(False),
        )
    )
    count = 0
    for tx in transactions:
        rule = match_rule(
            rules,
            MatchCandidate(
                counterparty_name=tx.counterparty_name,
                counterparty_iban=tx.counterparty_iban,
                description=tx.description,
            ),
        )
        if rule is None:
            continue
        category = categories[rule.category_id]
        tx.category_id = category.id
        tx.type = category.type  # type volgt de categorie (bv. Sparen)
        tx.categorization = Categorization.AUTO
        count += 1
    return count
