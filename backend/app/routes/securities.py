"""Beleggingen-endpoints (spec §7): effecten, transactielog, splits en portefeuille."""

from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.config import Settings, get_settings
from app.database import get_db
from app.models import Context, Security, SecurityPrice, SecuritySplit, SecurityTransaction
from app.schemas.investments import (
    PortfolioOut,
    PriceHistoryOut,
    PricePointOut,
    SecurityIn,
    SecurityOut,
    SecuritySearchHit,
    SecuritySplitIn,
    SecuritySplitOut,
    SecurityTransactionIn,
    SecurityTransactionOut,
)
from app.services.investments import build_portfolio
from app.services.prices import CHART_RANGES, fetch_chart_history, search_symbols
from app.services.securities import InvalidAmountError, apply_transaction, suggest_ticker

router = APIRouter(tags=["investments"])


def _security_out(security: Security) -> SecurityOut:
    return SecurityOut(
        id=security.id,
        name=security.name,
        ticker=security.ticker,
        isin=security.isin,
        owner_context_id=security.owner_context_id,
        soort=security.soort,
        is_benchmark=security.is_benchmark,
        suggested_ticker=suggest_ticker(security.name) if not security.ticker else None,
    )


def _get_context(db: Session, context_id: int) -> Context:
    context = db.get(Context, context_id)
    if context is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende context")
    return context


def _clear_other_benchmarks(db: Session, context_id: int, exclude_id: int | None) -> None:
    """Maximaal één referentie-index per context — een nieuwe markering vervangt de vorige."""
    query = select(Security).where(
        Security.owner_context_id == context_id, Security.is_benchmark.is_(True)
    )
    if exclude_id is not None:
        query = query.where(Security.id != exclude_id)
    for other in db.scalars(query):
        other.is_benchmark = False


def _get_security(db: Session, security_id: int) -> Security:
    security = db.get(Security, security_id)
    if security is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekend effect")
    return security


def _tx_out(tx: SecurityTransaction) -> SecurityTransactionOut:
    return SecurityTransactionOut(
        id=tx.id,
        security_id=tx.security_id,
        date=tx.date,
        side=tx.side,
        shares=str(tx.shares),
        price_per_share=str(tx.price_per_share),
        fee=str(tx.fee),
        tax=str(tx.tax),
        total=str(tx.total),
    )


# --- Effecten ---


@router.get("/api/securities", response_model=list[SecurityOut])
def list_securities(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    context_id: int,
) -> list[SecurityOut]:
    _get_context(db, context_id)
    rows = db.scalars(
        select(Security).where(Security.owner_context_id == context_id).order_by(Security.name)
    ).all()
    return [_security_out(s) for s in rows]


@router.get("/api/securities/search", response_model=list[SecuritySearchHit])
def search_securities(
    _user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    q: str,
) -> list[SecuritySearchHit]:
    if not settings.price_fetch_enabled:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Zoeken via Yahoo is uitgeschakeld"
        )
    if len(q.strip()) < 2:
        return []
    return [SecuritySearchHit(**hit) for hit in search_symbols(q.strip())]


@router.post("/api/securities", status_code=status.HTTP_201_CREATED, response_model=SecurityOut)
def create_security(
    body: SecurityIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> SecurityOut:
    _get_context(db, body.owner_context_id)
    if not body.name.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Naam is leeg")
    if body.is_benchmark:
        _clear_other_benchmarks(db, body.owner_context_id, exclude_id=None)
    security = Security(
        name=body.name.strip(),
        ticker=(body.ticker or None),
        isin=(body.isin or None),
        owner_context_id=body.owner_context_id,
        soort=body.soort,
        is_benchmark=body.is_benchmark,
    )
    db.add(security)
    db.commit()
    return _security_out(security)


@router.put("/api/securities/{security_id}", response_model=SecurityOut)
def update_security(
    security_id: int,
    body: SecurityIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> SecurityOut:
    security = _get_security(db, security_id)
    if body.owner_context_id != security.owner_context_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="De context van een effect is vast"
        )
    if body.is_benchmark:
        _clear_other_benchmarks(db, security.owner_context_id, exclude_id=security.id)
    security.name = body.name.strip()
    security.ticker = body.ticker or None
    security.isin = body.isin or None
    security.soort = body.soort
    security.is_benchmark = body.is_benchmark
    db.commit()
    return _security_out(security)


@router.delete("/api/securities/{security_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_security(
    security_id: int,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    security = _get_security(db, security_id)
    db.execute(delete(SecurityTransaction).where(SecurityTransaction.security_id == security_id))
    db.execute(delete(SecurityPrice).where(SecurityPrice.security_id == security_id))
    db.delete(security)
    db.commit()


@router.get("/api/securities/{security_id}/history", response_model=PriceHistoryOut)
def security_history(
    security_id: int,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    chart_range: Annotated[str, Query(alias="range")] = "1y",
) -> PriceHistoryOut:
    """Koersreeks voor de grafiek-popup, live van Yahoo (Yahoo-tijdsblokken)."""
    security = _get_security(db, security_id)
    if not settings.price_fetch_enabled:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Koersen ophalen is uitgeschakeld"
        )
    if not security.ticker:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Effect heeft geen ticker"
        )
    if chart_range not in CHART_RANGES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Onbekende periode")
    try:
        history = fetch_chart_history(security.ticker, chart_range)
    except Exception as exc:  # netwerk-/parse-fout bij Yahoo
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="Koershistoriek ophalen mislukt"
        ) from exc
    return PriceHistoryOut(
        security_id=security.id,
        ticker=security.ticker,
        range=chart_range,
        currency=history.currency,
        prev_close=str(history.prev_close) if history.prev_close is not None else None,
        points=[PricePointOut(t=p.t, price=str(p.price)) for p in history.points],
    )


# --- Transactielog ---


@router.get("/api/security-transactions", response_model=list[SecurityTransactionOut])
def list_transactions(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    security_id: int,
) -> list[SecurityTransactionOut]:
    _get_security(db, security_id)
    rows = db.scalars(
        select(SecurityTransaction)
        .where(SecurityTransaction.security_id == security_id)
        .order_by(SecurityTransaction.date, SecurityTransaction.id)
    ).all()
    return [_tx_out(tx) for tx in rows]


@router.post(
    "/api/security-transactions",
    status_code=status.HTTP_201_CREATED,
    response_model=SecurityTransactionOut,
)
def create_transaction(
    body: SecurityTransactionIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> SecurityTransactionOut:
    _get_security(db, body.security_id)
    tx = SecurityTransaction(security_id=body.security_id)
    try:
        apply_transaction(tx, body)
    except InvalidAmountError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    db.add(tx)
    db.commit()
    return _tx_out(tx)


@router.put("/api/security-transactions/{transaction_id}", response_model=SecurityTransactionOut)
def update_transaction(
    transaction_id: int,
    body: SecurityTransactionIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> SecurityTransactionOut:
    tx = db.get(SecurityTransaction, transaction_id)
    if tx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende transactie")
    try:
        apply_transaction(tx, body)
    except InvalidAmountError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    db.commit()
    return _tx_out(tx)


@router.delete(
    "/api/security-transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_transaction(
    transaction_id: int,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    tx = db.get(SecurityTransaction, transaction_id)
    if tx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende transactie")
    db.delete(tx)
    db.commit()


# --- Splits ---


def _split_out(split: SecuritySplit) -> SecuritySplitOut:
    return SecuritySplitOut(
        id=split.id, security_id=split.security_id, date=split.date, ratio=str(split.ratio)
    )


@router.get("/api/security-splits", response_model=list[SecuritySplitOut])
def list_splits(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    security_id: int,
) -> list[SecuritySplitOut]:
    _get_security(db, security_id)
    rows = db.scalars(
        select(SecuritySplit)
        .where(SecuritySplit.security_id == security_id)
        .order_by(SecuritySplit.date)
    ).all()
    return [_split_out(s) for s in rows]


@router.post(
    "/api/security-splits", status_code=status.HTTP_201_CREATED, response_model=SecuritySplitOut
)
def create_split(
    body: SecuritySplitIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> SecuritySplitOut:
    _get_security(db, body.security_id)
    invalid = HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Ongeldige ratio")
    try:
        ratio = Decimal(body.ratio)
    except InvalidOperation as exc:
        raise invalid from exc
    if ratio <= 0:
        raise invalid
    target = _get_security(db, body.security_id)
    split = SecuritySplit(security_id=target.id, date=body.date, ratio=ratio)
    db.add(split)

    if body.apply_to_other_contexts:
        # Zelfde effect bij de andere personen: match op ticker (indien gezet) of naam.
        for sibling in db.scalars(
            select(Security).where(
                Security.owner_context_id != target.owner_context_id,
                (Security.ticker == target.ticker)
                if target.ticker
                else (Security.name == target.name),
            )
        ):
            already = db.scalars(
                select(SecuritySplit).where(
                    SecuritySplit.security_id == sibling.id, SecuritySplit.date == body.date
                )
            ).first()
            if already is None:
                db.add(SecuritySplit(security_id=sibling.id, date=body.date, ratio=ratio))

    db.commit()
    return _split_out(split)


@router.delete("/api/security-splits/{split_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_split(
    split_id: int,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    split = db.get(SecuritySplit, split_id)
    if split is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende split")
    db.delete(split)
    db.commit()


# --- Portefeuille ---


@router.get("/api/portfolio", response_model=PortfolioOut)
def portfolio(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    context_id: int,
) -> PortfolioOut:
    context = _get_context(db, context_id)
    return build_portfolio(db, context)
