"""De drie recept-parsers achter POST /api/weekmenu/recipes/parse. Geen netwerk in tests."""

import base64
import json
from types import SimpleNamespace

import anthropic
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.weekmenu import parsing
from app.weekmenu.errors import WeekmenuError
from app.weekmenu.models import Ingredient, Recipe
from app.weekmenu.url_security import FetchResult

PARSE_URL = "/api/weekmenu/recipes/parse"

SCHEMA_ORG_HTML = """<html><head><script type="application/ld+json">
{"@context": "https://schema.org", "@type": "Recipe",
 "name": "Spaghetti bolognese",
 "recipeIngredient": ["500 g gehakt", "2 uien", "1 el olijfolie"],
 "recipeInstructions": [
   {"@type": "HowToStep", "text": "Fruit de ui."},
   {"@type": "HowToStep", "text": "Voeg het gehakt toe."}],
 "image": "https://example.com/foto.jpg"}
</script></head><body>Recept</body></html>"""

PLAIN_HTML = """<html><head><title>Blog</title><script>tracking();</script></head>
<body><nav>menu</nav><p>Vandaag maakte ik couscous met 200 g parelcouscous.</p></body></html>"""

CLAUDE_JSON = json.dumps(
    {
        "title": "Parelcouscous",
        "description": "Kook de couscous.",
        "photo_url": None,
        "source_url": None,
        "ingredients": [{"name": "parelcouscous", "quantity": "200", "unit": "g"}],
    }
)


def _fake_fetch(html: str, final_url: str = "https://example.com/recept"):
    def fake(url: str, max_bytes: int) -> FetchResult:
        return FetchResult(content=html.encode(), content_type="text/html", final_url=final_url)

    return fake


class _FakeMessages:
    def __init__(self, reply: str | None, error: Exception | None = None):
        self.reply = reply
        self.error = error
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.reply)])


def _patch_claude(
    monkeypatch: pytest.MonkeyPatch, reply: str | None, error: Exception | None = None
) -> _FakeMessages:
    """Vervang de Anthropic-client (incl. key-check) door een fake zonder netwerk."""
    messages = _FakeMessages(reply, error)
    monkeypatch.setattr(
        parsing, "get_claude_client", lambda settings: SimpleNamespace(messages=messages)
    )
    return messages


# --- Parser 1: URL met schema.org-metadata (recipe-scrapers, geen AI) ---


def test_parser1_schema_org(logged_in: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parsing, "fetch_url", _fake_fetch(SCHEMA_ORG_HTML))
    resp = logged_in.post(PARSE_URL, json={"url": "https://example.com/recept"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Spaghetti bolognese"
    assert "Fruit de ui." in data["description"]
    assert data["photo_url"] == "https://example.com/foto.jpg"
    assert data["source_url"] == "https://example.com/recept"
    assert data["ingredients"][0] == {"name": "gehakt", "quantity": "500", "unit": "g"}
    assert data["ingredients"][1] == {"name": "uien", "quantity": "2", "unit": None}
    assert data["ingredients"][2] == {"name": "olijfolie", "quantity": "1", "unit": "el"}


def test_parser1_slaat_niets_op(
    logged_in: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Parse geeft alleen een bewerkbaar object terug; er komt niets in de db."""
    monkeypatch.setattr(parsing, "fetch_url", _fake_fetch(SCHEMA_ORG_HTML))
    resp = logged_in.post(PARSE_URL, json={"url": "https://example.com/recept"})
    assert resp.status_code == 200
    assert db.query(Recipe).count() == 0
    assert db.query(Ingredient).count() == 0


def _build_nextjs_flight_html(base_html: str, recipe_parts: list[dict]) -> str:
    """Bouwt een Next.js flight-payload (``self.__next_f.push``) zoals VRT-sites die
    versturen: een dehydrated React Query-cache met het volledige ``recipeParts``.
    """
    body = json.dumps(
        {
            "state": {
                "queries": [
                    {"state": {"data": {"data": {"recipe": {
                        "recipeParts": recipe_parts,
                        "ingredients": [],
                    }}}}}
                ]
            }
        }
    )
    chunk = "15:" + body
    encoded = json.dumps(chunk)
    return base_html + f"<script>self.__next_f.push([1,{encoded}])</script>"


NEXTJS_FLIGHT_HTML = _build_nextjs_flight_html(
    SCHEMA_ORG_HTML,
    [
        {
            "title": "Voor de saus",
            "instructions": [
                {"description": "Fruit de ui en de look."},
                {"description": "Voeg de tomaten toe en laat 20 minuten sudderen."},
            ],
        },
        {
            "title": "Voor de pasta",
            "instructions": [{"description": "Kook de pasta beetgaar volgens de verpakking."}],
        },
    ],
)


def test_parser1_next_flight_payload_vult_afgekapte_schema_org_tekst_aan(
    logged_in: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regressietest: VRT Dagelijkse Kost zet in schema.org enkel de eerste stappen;
    het volledige stappenplan zit in een Next.js flight-payload verderop in de pagina."""
    monkeypatch.setattr(parsing, "fetch_url", _fake_fetch(NEXTJS_FLIGHT_HTML))
    resp = logged_in.post(PARSE_URL, json={"url": "https://example.com/recept"})
    assert resp.status_code == 200
    description = resp.json()["description"]
    assert "Voor de saus:" in description
    assert "Voor de pasta:" in description
    assert "Kook de pasta beetgaar volgens de verpakking." in description
    # De korte schema.org-tekst ("Fruit de ui.") is vervangen, niet enkel aangevuld.
    assert "Voeg het gehakt toe." not in description


def test_extract_nextjs_flight_description_geeft_none_zonder_match() -> None:
    assert parsing._extract_nextjs_flight_description(SCHEMA_ORG_HTML) is None
    assert parsing._extract_nextjs_flight_description("<html>niets hier</html>") is None


def test_parser1_dode_url_geeft_nette_fout(
    logged_in: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def dead(url: str, max_bytes: int) -> FetchResult:
        raise WeekmenuError(502, "fetch_failed", "De pagina kon niet opgehaald worden.")

    monkeypatch.setattr(parsing, "fetch_url", dead)
    resp = logged_in.post(PARSE_URL, json={"url": "https://example.com/dood"})
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "fetch_failed"


def test_parse_interne_url_geweigerd(logged_in: TestClient) -> None:
    """SSRF-check zit vóór de fetch — geen mock nodig, er mag geen netwerk aan te pas komen."""
    resp = logged_in.post(PARSE_URL, json={"url": "http://127.0.0.1:8000/admin"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_url"


# --- Parser 2: URL-fallback zonder schema (Claude op gestripte HTML-tekst) ---


def test_parser2_fallback_naar_claude(
    logged_in: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(parsing, "fetch_url", _fake_fetch(PLAIN_HTML))
    messages = _patch_claude(monkeypatch, CLAUDE_JSON)
    resp = logged_in.post(PARSE_URL, json={"url": "https://example.com/recept"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Parelcouscous"
    assert data["source_url"] == "https://example.com/recept"  # server vult bron-URL in
    assert data["ingredients"] == [{"name": "parelcouscous", "quantity": "200", "unit": "g"}]
    # De prompt bevat de gestripte paginatekst, zonder script/nav.
    prompt = messages.calls[0]["messages"][0]["content"][0]["text"]
    assert "parelcouscous" in prompt
    assert "tracking" not in prompt
    assert "menu" not in prompt


def test_parser2_kapotte_json_geeft_502(
    logged_in: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(parsing, "fetch_url", _fake_fetch(PLAIN_HTML))
    _patch_claude(monkeypatch, "Dit is geen JSON, sorry!")
    resp = logged_in.post(PARSE_URL, json={"url": "https://example.com/recept"})
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "ai_invalid_response"


def test_parser2_zonder_api_key_geeft_503(
    logged_in: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test-Settings hebben een lege anthropic_api_key; de echte key-check draait."""
    monkeypatch.setattr(parsing, "fetch_url", _fake_fetch(PLAIN_HTML))
    resp = logged_in.post(PARSE_URL, json={"url": "https://example.com/recept"})
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "ai_unavailable"


def test_parser2_json_met_fences_wordt_gestript(
    logged_in: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(parsing, "fetch_url", _fake_fetch(PLAIN_HTML))
    _patch_claude(monkeypatch, f"```json\n{CLAUDE_JSON}\n```")
    resp = logged_in.post(PARSE_URL, json={"url": "https://example.com/recept"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Parelcouscous"


# --- Parser 3: afbeelding/screenshot naar Claude vision ---

IMAGE_B64 = base64.b64encode(b"fake-jpeg-bytes").decode()


def test_parser3_afbeelding(logged_in: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    messages = _patch_claude(monkeypatch, CLAUDE_JSON)
    resp = logged_in.post(
        PARSE_URL, json={"image_base64": IMAGE_B64, "image_media_type": "image/jpeg"}
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Parelcouscous"
    content = messages.calls[0]["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"] == {
        "type": "base64",
        "media_type": "image/jpeg",
        "data": IMAGE_B64,
    }


def test_parser3_api_fout_geeft_502(logged_in: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_claude(monkeypatch, None, error=anthropic.AnthropicError("api kapot"))
    resp = logged_in.post(
        PARSE_URL, json={"image_base64": IMAGE_B64, "image_media_type": "image/jpeg"}
    )
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "ai_failed"


@pytest.mark.parametrize(
    "payload",
    [
        {"image_base64": "geen@geldige@base64!!", "image_media_type": "image/jpeg"},
        {"image_base64": IMAGE_B64, "image_media_type": "text/html"},
        {"image_base64": IMAGE_B64},  # media type ontbreekt
    ],
)
def test_parser3_ongeldige_afbeelding_geeft_422(logged_in: TestClient, payload: dict) -> None:
    assert logged_in.post(PARSE_URL, json=payload).status_code == 422


# --- Algemene randgevallen ---


def test_parse_vereist_login(client: TestClient) -> None:
    resp = client.post(PARSE_URL, json={"url": "https://example.com/recept"})
    assert resp.status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            "url": "https://example.com/r",
            "image_base64": IMAGE_B64,
            "image_media_type": "image/jpeg",
        },
    ],
)
def test_parse_precies_een_bron_verplicht(logged_in: TestClient, payload: dict) -> None:
    assert logged_in.post(PARSE_URL, json=payload).status_code == 422


# --- Unit: ingrediëntregel-heuristiek ---


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("500 g gehakt", ("gehakt", "500", "g")),
        ("2 uien", ("uien", "2", None)),
        ("1,5 dl room", ("room", "1,5", "dl")),
        ("peper en zout", ("peper en zout", None, None)),
        ("½ komkommer", ("komkommer", "½", None)),
    ],
)
def test_split_ingredient_line(line: str, expected: tuple) -> None:
    parsed = parsing.split_ingredient_line(line)
    assert (parsed.name, parsed.quantity, parsed.unit) == expected
