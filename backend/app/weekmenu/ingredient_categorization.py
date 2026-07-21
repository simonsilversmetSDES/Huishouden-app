"""Automatische winkelcategorie voor NIEUW aangemaakte ingrediënten (Claude API).

Wordt aangeroepen vanuit crud.py, uitsluitend voor ingrediënten die bij het opslaan
van een recept net voor het eerst zijn aangemaakt — bestaande ingrediënten (ook als
ze nog geen categorie hebben) worden hier nooit aan getoetst, zodat een handmatige
keuze (of een bewust lege categorie) nooit stilzwijgend overschreven wordt.

Niet-fataal, net als de foto-download: geen API-key, netwerkfout of onbruikbaar
antwoord van Claude betekent gewoon dat de nieuwe ingrediënten ongecategoriseerd
blijven (shopping_category_id = None) — het opslaan van het recept faalt hier nooit op.
"""

import json
import logging
import re

import anthropic

from app.config import Settings
from app.weekmenu.errors import WeekmenuError
from app.weekmenu.models import ShoppingCategory
from app.weekmenu.parsing import get_claude_client

logger = logging.getLogger(__name__)

CATEGORIZE_MAX_TOKENS = 1024

_PROMPT = (
    "Je krijgt een lijst met Nederlandse boodschappen-ingrediënten en een lijst met "
    "winkelcategorieën. Ken elk ingrediënt de best passende categorie toe.\n\n"
    "Ingrediënten: {names}\n"
    "Categorieën: {categories}\n\n"
    "Antwoord met UITSLUITEND geldige JSON: een object met exact de ingrediëntnamen als "
    "sleutels en de gekozen categorienaam (letterlijk overgenomen uit de categorieënlijst) "
    "als waarde. Gebruik null als geen enkele categorie goed past. Geen uitleg, geen "
    "markdown-fences."
)


def _parse_mapping(raw: str) -> dict[str, str | None] | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text.strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def classify_ingredients(
    names: list[str], categories: list[ShoppingCategory], settings: Settings
) -> dict[str, int]:
    """Vraag Claude om per naam de beste winkelcategorie; geeft {naam: category_id} terug
    voor de namen waarover Claude een geldige keuze maakte (ontbrekende/mislukte namen
    blijven gewoon weg uit het resultaat)."""
    if not names or not categories:
        return {}
    try:
        client = get_claude_client(settings)
    except WeekmenuError:
        return {}

    category_names = [c.name for c in categories]
    prompt = _PROMPT.format(
        names=json.dumps(names, ensure_ascii=False),
        categories=json.dumps(category_names, ensure_ascii=False),
    )
    try:
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=CATEGORIZE_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AnthropicError:
        logger.warning("Ingrediënt-categorisering mislukt (Claude-fout)", exc_info=True)
        return {}

    raw = "".join(block.text for block in response.content if block.type == "text")
    mapping = _parse_mapping(raw)
    if mapping is None:
        logger.warning("Ingrediënt-categorisering mislukt: onbruikbaar antwoord: %r", raw)
        return {}

    name_to_id = {c.name.strip().lower(): c.id for c in categories}
    result: dict[str, int] = {}
    for name in names:
        chosen = mapping.get(name)
        if not isinstance(chosen, str):
            continue
        category_id = name_to_id.get(chosen.strip().lower())
        if category_id is not None:
            result[name] = category_id
    return result
