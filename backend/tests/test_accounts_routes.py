"""Rekeningen-CRUD (spec §6): toevoegen, hernoemen, soft-delete, per context."""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AccountSnapshot, Context


def _context_id(db: Session, name: str = "Simon") -> int:
    return db.scalars(select(Context).where(Context.name == name)).one().id


def _body(context_id: int, name: str = "Vrije ruimte Degiro", type_: str = "belegging") -> dict:
    return {"context_id": context_id, "name": name, "type": type_}


class TestAccountsCrud:
    def test_vereist_login(self, client: TestClient) -> None:
        assert client.post("/api/accounts", json=_body(1)).status_code == 401

    def test_toevoegen_en_lijsten(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _context_id(seeded_db)
        resp = logged_in.post("/api/accounts", json=_body(ctx))
        assert resp.status_code == 201
        acc_id = resp.json()["id"]
        listed = logged_in.get("/api/accounts", params={"context_id": ctx}).json()
        assert acc_id in [a["id"] for a in listed]

    def test_hernoemen(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _context_id(seeded_db)
        acc_id = logged_in.post("/api/accounts", json=_body(ctx)).json()["id"]
        resp = logged_in.put(
            f"/api/accounts/{acc_id}", json=_body(ctx, name="Vrije ruimte Bolero")
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Vrije ruimte Bolero"

    def test_duplicaat_409(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _context_id(seeded_db)
        logged_in.post("/api/accounts", json=_body(ctx, name="Groepsverzekering"))
        resp = logged_in.post("/api/accounts", json=_body(ctx, name="Groepsverzekering"))
        assert resp.status_code == 409

    def test_soft_delete_behoudt_snapshots(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _context_id(seeded_db)
        acc_id = logged_in.post("/api/accounts", json=_body(ctx)).json()["id"]
        seeded_db.add(
            AccountSnapshot(
                account_id=acc_id, snapshot_date=date(2026, 6, 1), balance=Decimal("100.00")
            )
        )
        seeded_db.commit()

        assert logged_in.delete(f"/api/accounts/{acc_id}").status_code == 204
        listed = logged_in.get("/api/accounts", params={"context_id": ctx}).json()
        assert acc_id not in [a["id"] for a in listed]  # verborgen uit de lijst
        # snapshot blijft bestaan; account bestaat nog (inactief)
        assert seeded_db.get(Account, acc_id).active is False
        assert seeded_db.scalars(select(AccountSnapshot)).all()

    def test_toevoegen_reactiveert(self, logged_in: TestClient, seeded_db: Session) -> None:
        ctx = _context_id(seeded_db)
        acc_id = logged_in.post("/api/accounts", json=_body(ctx)).json()["id"]
        logged_in.delete(f"/api/accounts/{acc_id}")
        resp = logged_in.post("/api/accounts", json=_body(ctx))  # zelfde naam
        assert resp.status_code == 201
        assert resp.json()["id"] == acc_id

    def test_context_scheiding(self, logged_in: TestClient, seeded_db: Session) -> None:
        simon = _context_id(seeded_db, "Simon")
        joz = _context_id(seeded_db, "Jozefien")
        logged_in.post("/api/accounts", json=_body(simon, name="Vrije ruimte Degiro"))
        joz_names = [
            a["name"] for a in logged_in.get("/api/accounts", params={"context_id": joz}).json()
        ]
        assert "Vrije ruimte Degiro" not in joz_names
