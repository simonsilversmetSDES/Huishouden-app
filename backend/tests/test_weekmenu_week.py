"""Weekplanning (Fase 4): GET /week (7-daagse synthese) en PUT /week/{dag} (upsert)."""

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.weekmenu.models import WeekPlanEntry

WEEK_URL = "/api/weekmenu/week"
MONDAY = date(2026, 7, 20)  # ma 20/07/2026


def _create_recipe(client: TestClient, title: str = "Spaghetti bolognese") -> int:
    resp = client.post("/api/weekmenu/recipes", json={"title": title, "ingredients": []})
    assert resp.status_code == 201
    return resp.json()["id"]


# --- GET /week ---


def test_lege_week_geeft_zeven_lege_dagen(logged_in: TestClient) -> None:
    resp = logged_in.get(WEEK_URL, params={"start": MONDAY.isoformat()})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 7
    assert [d["date"] for d in data] == [(MONDAY + timedelta(days=i)).isoformat() for i in range(7)]
    assert all(
        d["recipe_id"] is None and d["recipe_title"] is None and d["free_text"] is None
        and d["checked"] is False
        for d in data
    )


def test_dag_met_recept_toont_titel_rest_blijft_leeg(logged_in: TestClient) -> None:
    recipe_id = _create_recipe(logged_in)
    resp = logged_in.put(
        f"{WEEK_URL}/{MONDAY.isoformat()}", json={"recipe_id": recipe_id, "checked": False}
    )
    assert resp.status_code == 200

    data = logged_in.get(WEEK_URL, params={"start": MONDAY.isoformat()}).json()
    monday_entry = data[0]
    assert monday_entry["recipe_id"] == recipe_id
    assert monday_entry["recipe_title"] == "Spaghetti bolognese"
    assert all(d["recipe_id"] is None for d in data[1:])


def test_week_vereist_login(client: TestClient) -> None:
    assert client.get(WEEK_URL, params={"start": MONDAY.isoformat()}).status_code == 401


# --- PUT /week/{dag} ---


def test_put_met_recipe_id(logged_in: TestClient) -> None:
    recipe_id = _create_recipe(logged_in)
    resp = logged_in.put(f"{WEEK_URL}/{MONDAY.isoformat()}", json={"recipe_id": recipe_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["recipe_id"] == recipe_id
    assert data["free_text"] is None


def test_put_met_vrije_tekst(logged_in: TestClient) -> None:
    resp = logged_in.put(f"{WEEK_URL}/{MONDAY.isoformat()}", json={"free_text": "Bbq"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["free_text"] == "Bbq"
    assert data["recipe_id"] is None


def test_put_recipe_en_vrije_tekst_samen_geeft_422(logged_in: TestClient) -> None:
    recipe_id = _create_recipe(logged_in)
    resp = logged_in.put(
        f"{WEEK_URL}/{MONDAY.isoformat()}",
        json={"recipe_id": recipe_id, "free_text": "Bbq"},
    )
    assert resp.status_code == 422


def test_put_checked_zonder_inhoud_geeft_422(logged_in: TestClient) -> None:
    resp = logged_in.put(f"{WEEK_URL}/{MONDAY.isoformat()}", json={"checked": True})
    assert resp.status_code == 422


def test_put_checked_met_recept_is_toegestaan(logged_in: TestClient) -> None:
    recipe_id = _create_recipe(logged_in)
    resp = logged_in.put(
        f"{WEEK_URL}/{MONDAY.isoformat()}", json={"recipe_id": recipe_id, "checked": True}
    )
    assert resp.status_code == 200
    assert resp.json()["checked"] is True


def test_put_checked_met_vrije_tekst_is_toegestaan(logged_in: TestClient) -> None:
    resp = logged_in.put(
        f"{WEEK_URL}/{MONDAY.isoformat()}", json={"free_text": "Bbq", "checked": True}
    )
    assert resp.status_code == 200
    assert resp.json()["checked"] is True


def test_put_onbekend_recipe_id_geeft_400(logged_in: TestClient) -> None:
    resp = logged_in.put(f"{WEEK_URL}/{MONDAY.isoformat()}", json={"recipe_id": 999})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unknown_attribute"


def test_put_op_bestaande_dag_is_upsert_geen_dubbele_rij(
    logged_in: TestClient, db: Session
) -> None:
    recipe_id = _create_recipe(logged_in)
    logged_in.put(f"{WEEK_URL}/{MONDAY.isoformat()}", json={"recipe_id": recipe_id})
    resp = logged_in.put(f"{WEEK_URL}/{MONDAY.isoformat()}", json={"free_text": "Bbq"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["recipe_id"] is None
    assert data["free_text"] == "Bbq"
    assert db.query(WeekPlanEntry).filter(WeekPlanEntry.date == MONDAY).count() == 1


def test_put_vereist_login(client: TestClient) -> None:
    resp = client.put(f"{WEEK_URL}/{MONDAY.isoformat()}", json={"free_text": "Bbq"})
    assert resp.status_code == 401
