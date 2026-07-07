"""Beleggingen-endpoints (spec §7): effecten, transactielog en portefeuille."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.database import get_db
from app.models import Context, Security, SecurityPrice, SecurityTransaction
from app.schemas.investments import (
    PortfolioOut,
    SecurityIn,
    SecurityOut,
    SecurityTransactionIn,
    SecurityTransactionOut,
)
from app.services.investments import build_portfolio
from app.services.securities import InvalidAmountError, apply_transaction

router = APIRouter(tags=["investments"])


def _get_context(db: Session, context_id: int) -> Context:
    context = db.get(Context, context_id)
    if context is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Onbekende context")
    return context


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
) -> list[Security]:
    _get_context(db, context_id)
    return list(
        db.scalars(
            select(Security)
            .where(Security.owner_context_id == context_id)
            .order_by(Security.name)
        ).all()
    )


@router.post("/api/securities", status_code=status.HTTP_201_CREATED, response_model=SecurityOut)
def create_security(
    body: SecurityIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Security:
    _get_context(db, body.owner_context_id)
    if not body.name.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Naam is leeg")
    security = Security(
        name=body.name.strip(),
        ticker=(body.ticker or None),
        isin=(body.isin or None),
        owner_context_id=body.owner_context_id,
    )
    db.add(security)
    db.commit()
    return security


@router.put("/api/securities/{security_id}", response_model=SecurityOut)
def update_security(
    security_id: int,
    body: SecurityIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Security:
    security = _get_security(db, security_id)
    if body.owner_context_id != security.owner_context_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="De context van een effect is vast"
        )
    security.name = body.name.strip()
    security.ticker = body.ticker or None
    security.isin = body.isin or None
    db.commit()
    return security


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


# --- Portefeuille ---


@router.get("/api/portfolio", response_model=PortfolioOut)
def portfolio(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    context_id: int,
) -> PortfolioOut:
    context = _get_context(db, context_id)
    return build_portfolio(db, context)
