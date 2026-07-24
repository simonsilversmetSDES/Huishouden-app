"""Extra categorisatie-lagen voor de CSV-import, bovenop de regelengine (spec §5.3).

Volgorde van precedentie in de preview (zie bank_import.build_preview):

1. Regels (services/rules.py) — expliciete gebruikersintentie, first-match-wins.
2. Historiek (hier, `build_history_resolver`) — deterministisch, géén netwerk: neem
   de dominante categorie over van eerdere, gecategoriseerde transacties met dezelfde
   tegenpartij (eerst op IBAN, anders op genormaliseerde naam).
3. AI-fallback (hier, `suggest_categories_ai`) — enkel voor wat na 1+2 nog leeg is:
   tegenpartij + omschrijving gaan server-side naar de Claude API voor een suggestie.

Lagen 2 en 3 maken NOOIT een regel aan — dat is net het punt (categoriseren zonder
voor alles een regel te moeten schrijven). De AI-laag is niet-fataal en uitschakelbaar,
net als de weekmenu-parsing: geen key, laag uitgeschakeld, netwerkfout of onbruikbaar
antwoord → die rijen blijven gewoon ongecategoriseerd. De Anthropic-key blijft
server-side (backend/.env) en wordt nooit naar de frontend gestuurd.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Category, Transaction
from app.models.enums import CategoryType
from app.services.csv_parsers import normalize_iban

logger = logging.getLogger(__name__)

AI_CATEGORIZE_MAX_TOKENS = 2048
# Bovengrens op het aantal historische voorbeelden in de AI-prompt: genoeg om de
# categorie-stijl van de gebruiker mee te geven, zonder de prompt te laten ontsporen.
_MAX_AI_EXAMPLES = 40


def _normalize_name(name: str | None) -> str | None:
    """Tegenpartijnaam vergelijkbaar maken: witruimte pletten + casefold."""
    if not name:
        return None
    collapsed = " ".join(name.split()).casefold()
    return collapsed or None


@dataclass(frozen=True)
class TxCandidate:
    """Wat een historiek-/AI-laag van een te categoriseren rij nodig heeft."""

    counterparty_name: str | None
    counterparty_iban: str | None
    description: str | None
    amount_cents: int


class HistoryResolver:
    """Dominante categorie per tegenpartij, afgeleid uit eerdere transacties.

    Enkel categorieën die in de context nog actief zijn tellen mee: een transactie die
    naar een intussen gedeactiveerde categorie wees, mag niet terug opduiken. IBAN is
    specifieker dan naam en wint. `examples` levert (tegenpartij → categorienaam)-paren
    voor de AI-prompt, zodat die de categorie-stijl van de gebruiker leert.
    """

    def __init__(
        self,
        by_iban: dict[str, Category],
        by_name: dict[str, Category],
        examples: list[tuple[str, str]],
    ) -> None:
        self._by_iban = by_iban
        self._by_name = by_name
        self.examples = examples

    def resolve(self, candidate: TxCandidate) -> Category | None:
        if candidate.counterparty_iban:
            hit = self._by_iban.get(normalize_iban(candidate.counterparty_iban))
            if hit is not None:
                return hit
        name = _normalize_name(candidate.counterparty_name)
        if name is not None:
            return self._by_name.get(name)
        return None


def build_history_resolver(db: Session, context_id: int) -> HistoryResolver:
    active: dict[int, Category] = {
        c.id: c
        for c in db.scalars(
            select(Category).where(Category.context_id == context_id, Category.active)
        )
    }
    iban_counts: dict[str, Counter[int]] = defaultdict(Counter)
    name_counts: dict[str, Counter[int]] = defaultdict(Counter)

    rows = db.execute(
        select(
            Transaction.counterparty_iban,
            Transaction.counterparty_name,
            Transaction.category_id,
        ).where(
            Transaction.context_id == context_id,
            Transaction.category_id.is_not(None),
            Transaction.is_internal_transfer.is_(False),
        )
    ).all()
    for iban, name, category_id in rows:
        if category_id not in active:  # gedeactiveerde categorie → overslaan
            continue
        if iban:
            iban_counts[normalize_iban(iban)][category_id] += 1
        norm_name = _normalize_name(name)
        if norm_name is not None:
            name_counts[norm_name][category_id] += 1

    def dominant(counts: dict[str, Counter[int]]) -> dict[str, Category]:
        # most_common(1) is stabiel voor gelijke standen (invoegvolgorde); goed genoeg.
        return {key: active[counter.most_common(1)[0][0]] for key, counter in counts.items()}

    by_iban = dominant(iban_counts)
    by_name = dominant(name_counts)

    examples: list[tuple[str, str]] = []
    seen: set[str] = set()
    for norm_name, category in by_name.items():
        if norm_name in seen:
            continue
        seen.add(norm_name)
        examples.append((norm_name, category.name))
        if len(examples) >= _MAX_AI_EXAMPLES:
            break

    return HistoryResolver(by_iban, by_name, examples)


_AI_PROMPT = (
    "Je bent een boekhoudkundige assistent. Je krijgt banktransacties en een lijst met "
    "budgetcategorieën. Ken elke transactie de best passende categorie toe op basis van de "
    "tegenpartij en de omschrijving. Positieve bedragen zijn inkomsten, negatieve uitgaven.\n\n"
    "Categorieën (JSON): {categories}\n\n"
    "{examples}"
    "Transacties (JSON, per index): {transactions}\n\n"
    "Antwoord met UITSLUITEND geldige JSON: een object met de index (als string) als sleutel "
    "en de gekozen categorienaam (letterlijk overgenomen uit de lijst) als waarde. Gebruik null "
    "wanneer geen enkele categorie duidelijk past — gok niet. Geen uitleg, geen markdown-fences."
)


def _client(settings: Settings) -> anthropic.Anthropic | None:
    """Eigen client (bewust niet gedeeld met weekmenu, om de features te ontkoppelen).
    None wanneer geen key geconfigureerd is → laag stilzwijgend uitgeschakeld."""
    if not settings.anthropic_api_key:
        return None
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _parse_mapping(raw: str) -> dict | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text.strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _resolve_name(
    chosen: str, amount_cents: int, by_name: dict[str, list[Category]]
) -> int | None:
    """Categorienaam → id. Bij een naam die in meerdere types bestaat (namen zijn enkel
    uniek per type), kies het type dat bij het teken van het bedrag past."""
    options = by_name.get(chosen.strip().lower())
    if not options:
        return None
    if len(options) == 1:
        return options[0].id
    preferred = (
        [CategoryType.INKOMEN]
        if amount_cents > 0
        else [CategoryType.UITGAVEN, CategoryType.SPAREN]
    )
    for wanted in preferred:
        for category in options:
            if category.type == wanted:
                return category.id
    return options[0].id


def suggest_categories_ai(
    candidates: list[TxCandidate],
    categories: list[Category],
    settings: Settings,
    examples: list[tuple[str, str]] | None = None,
) -> dict[int, int]:
    """Vraag Claude per (index van de) kandidaat de best passende categorie.

    Geeft {index → category_id} terug voor de kandidaten waarover Claude een geldige keuze
    maakte; ontbrekende/mislukte indexen blijven gewoon weg. Niet-fataal: geen key, de laag
    uitgeschakeld, een netwerkfout of een onbruikbaar antwoord → lege dict.
    """
    if not candidates or not categories or not settings.import_ai_categorization_enabled:
        return {}
    client = _client(settings)
    if client is None:
        return {}

    category_payload = [{"naam": c.name, "type": c.type.value} for c in categories]
    tx_payload = {
        str(i): {
            "tegenpartij": c.counterparty_name,
            "omschrijving": c.description,
            "bedrag_eur": round(c.amount_cents / 100, 2),
        }
        for i, c in enumerate(candidates)
    }
    examples_block = ""
    if examples:
        pairs = {name: cat for name, cat in examples}
        examples_block = (
            "Eerdere toewijzingen van deze gebruiker (tegenpartij → categorie), als leidraad "
            f"voor de stijl: {json.dumps(pairs, ensure_ascii=False)}\n\n"
        )
    prompt = _AI_PROMPT.format(
        categories=json.dumps(category_payload, ensure_ascii=False),
        examples=examples_block,
        transactions=json.dumps(tx_payload, ensure_ascii=False),
    )

    try:
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=AI_CATEGORIZE_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AnthropicError:
        logger.warning("AI-categorisatie mislukt (Claude-fout)", exc_info=True)
        return {}

    raw = "".join(block.text for block in response.content if block.type == "text")
    mapping = _parse_mapping(raw)
    if mapping is None:
        logger.warning("AI-categorisatie mislukt: onbruikbaar antwoord: %r", raw)
        return {}

    by_name: dict[str, list[Category]] = defaultdict(list)
    for category in categories:
        by_name[category.name.strip().lower()].append(category)

    result: dict[int, int] = {}
    for index_str, chosen in mapping.items():
        if not isinstance(chosen, str):
            continue
        try:
            index = int(index_str)
        except (TypeError, ValueError):
            continue
        if not 0 <= index < len(candidates):
            continue
        category_id = _resolve_name(chosen, candidates[index].amount_cents, by_name)
        if category_id is not None:
            result[index] = category_id
    return result
