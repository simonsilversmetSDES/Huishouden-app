"""Categorisatieregels (spec §5.3): CRUD + retroactief toepassen.

De regelengine zelf zit in `services/rules.py`; deze routes ontsluiten het beheer
ervan en het toepassen op ongecategoriseerde transacties. Regex-regels worden bij
het aanmaken/wijzigen gevalideerd (de engine slaat een kapotte regex bij het
matchen stil over — hier weigeren we ze net).
"""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.database import get_db
from app.models import CategorizationRule, Category, Context
from app.models.enums import MatchType
from app.schemas.rules import RuleApplyResult, RuleIn, RuleOut
from app.services.rules import apply_rules

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _get_context(db: Session, context_id: int) -> Context:
    context = db.get(Context, context_id)
    if context is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende context")
    return context


def _validated_category(db: Session, context_id: int, category_id: int) -> Category:
    category = db.get(Category, category_id)
    if category is None or category.context_id != context_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Onbekende categorie voor deze context"
        )
    return category


def _validate_match_value(match_type: MatchType, match_value: str) -> str:
    value = match_value.strip()
    if not value:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Matchwaarde is leeg")
    if match_type == MatchType.REGEX:
        try:
            re.compile(value)
        except re.error as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Ongeldige regex: {exc}"
            ) from exc
    return value


def _to_out(rule: CategorizationRule, category_name: str | None) -> RuleOut:
    return RuleOut(
        id=rule.id,
        context_id=rule.context_id,
        priority=rule.priority,
        match_field=rule.match_field,
        match_type=rule.match_type,
        match_value=rule.match_value,
        category_id=rule.category_id,
        category_name=category_name,
        created_from_correction=rule.created_from_correction,
    )


def _get_rule(db: Session, rule_id: int) -> CategorizationRule:
    rule = db.get(CategorizationRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende regel")
    return rule


@router.get("", response_model=list[RuleOut])
def list_rules(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    context_id: int,
) -> list[RuleOut]:
    _get_context(db, context_id)
    rules = db.scalars(
        select(CategorizationRule)
        .where(CategorizationRule.context_id == context_id)
        .order_by(CategorizationRule.priority, CategorizationRule.id)
    ).all()
    # Geen relationships op de modellen (conventie): categorienamen via één query.
    names = dict(
        db.execute(
            select(Category.id, Category.name).where(Category.context_id == context_id)
        ).all()
    )
    return [_to_out(rule, names.get(rule.category_id)) for rule in rules]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RuleOut)
def create_rule(
    body: RuleIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> RuleOut:
    _get_context(db, body.context_id)
    category = _validated_category(db, body.context_id, body.category_id)
    match_value = _validate_match_value(body.match_type, body.match_value)
    rule = CategorizationRule(
        context_id=body.context_id,
        priority=body.priority,
        match_field=body.match_field,
        match_type=body.match_type,
        match_value=match_value,
        category_id=body.category_id,
        created_from_correction=body.created_from_correction,
    )
    db.add(rule)
    db.commit()
    return _to_out(rule, category.name)


@router.put("/{rule_id}", response_model=RuleOut)
def update_rule(
    rule_id: int,
    body: RuleIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> RuleOut:
    rule = _get_rule(db, rule_id)
    if body.context_id != rule.context_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="De context van een regel is niet wijzigbaar",
        )
    category = _validated_category(db, rule.context_id, body.category_id)
    match_value = _validate_match_value(body.match_type, body.match_value)
    rule.priority = body.priority
    rule.match_field = body.match_field
    rule.match_type = body.match_type
    rule.match_value = match_value
    rule.category_id = body.category_id
    rule.created_from_correction = body.created_from_correction
    db.commit()
    return _to_out(rule, category.name)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: int,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    rule = _get_rule(db, rule_id)
    db.delete(rule)
    db.commit()


@router.post("/apply", response_model=RuleApplyResult)
def apply_rules_route(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    context_id: int,
    rule_id: Annotated[int | None, Query()] = None,
) -> RuleApplyResult:
    _get_context(db, context_id)
    updated = apply_rules(db, context_id, rule_id)
    db.commit()
    return RuleApplyResult(updated_count=updated)
