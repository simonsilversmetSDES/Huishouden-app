"""Canonicaliseren van ingrediëntnamen.

De GESCHREVEN naam ("verse munt", "2 dikke wortelen", "bolletje zwarte peper") blijft
zichtbaar in het recept (opgeslagen als ``recipe_ingredients.display_name``); het
CANONIEKE ingrediënt eronder ("munt", "wortelen", "peper") draagt de dedupe-sleutel,
het voorraadtype en de winkelcategorie.

``canonicalize_ingredient_name`` doet twee dingen, in deze volgorde:
1. maat-/portiewoorden, subjectieve adjectieven en merknamen vooraan afpellen;
2. het resultaat door een synoniemen-tabel halen die spellings-/enkelvoud-meervoud- en
   semantische varianten samenvoegt (bv. "uien" → "ui", "zwarte peper" → "peper").

Zowel de opslag (crud) als de eenmalige opschoonmigratie gebruiken deze functie, zodat
bestaande én nieuwe ingrediënten identiek gecanonicaliseerd worden.

Herb-detectie (``is_herb``) staat hier ook, zodat het voorraadtype "Kruiden" op één
plek gedefinieerd is.
"""

import re

# Toelichtingen tussen haakjes horen niet in de canonieke naam ("Harissa (naar smaak)"
# → "Harissa"; "tomatenpulp (blik)" → "tomatenpulp").
_PARENTHETICAL_RE = re.compile(r"\s*\([^)]*\)")

# Maat-/portie-/hoeveelheidswoorden die vooraan mogen wegvallen (naast een eventueel
# getal). Ruimer dan parsing._KNOWN_UNITS omdat hier ook losse portiewoorden staan die
# geen echte eenheid zijn ("bolletje", "dopje", "handvol").
_MEASURE_PREFIXES = frozenset({
    "een", "enkele", "wat", "paar", "beetje", "stukje", "stuk", "stukjes",
    "snuf", "snufje", "snuifje", "sniff", "mespunt", "mespuntje", "scheut", "scheutje",
    "takje", "takjes", "blaadje", "blaadjes", "bolletje", "bol", "dopje", "klontje",
    "toef", "toefje", "handvol", "teentje", "teen", "tenen", "plantje", "bussel",
    "bussels", "bakje", "blik", "blikje", "blikjes", "vel", "stronkje",
    "kl", "el", "tl", "deciliter", "liter", "gram", "kilo", "mix",
})

# Subjectieve/grootte-/versheidsbijvoeglijke naamwoorden die niets over het product
# zelf zeggen. Kleuren (witte/rode/groene/zwarte) en bereidingswijzen (gerookte,
# geraspte, halfvolle) staan er bewust NIET in — die kunnen een ander product aanduiden.
_ADJECTIVE_PREFIXES = frozenset({
    "verse", "vers", "dikke", "dik", "grote", "groot", "kleine", "klein",
    "gedroogde", "gedroogd", "fijngesneden", "gemalen",
})

# Verbindingswoorden die als leftover vooraan kunnen blijven staan na het afpellen van
# een maatwoord ("mix van kerstomaatjes" → "kerstomaatjes").
_CONNECTOR_PREFIXES = frozenset({"van", "met"})

# Merknamen (nl-BE retail) die vooraan weggestript worden.
_BRAND_PREFIXES = frozenset({
    "boni", "spar", "delhaize", "colruyt", "aldi", "lidl", "everyday", "ah",
})

_STRIPPABLE = _MEASURE_PREFIXES | _ADJECTIVE_PREFIXES | _BRAND_PREFIXES | _CONNECTOR_PREFIXES

# Synoniemen: genormaliseerde (lowercase) variant → canonieke weergavenaam. Toegepast
# NA het afpellen van voorvoegsels. Vangt spellings-/enkelvoud-meervoud- en semantische
# varianten die geen prefix-regel dekt. Vrij uit te breiden.
_SYNONYMS: dict[str, str] = {
    # enkelvoud/meervoud
    "uien": "ui",
    "wortel": "wortelen",
    "wortels": "wortelen",
    "tomaten": "tomaat",
    "courgettes": "courgette",
    "ronde courgettes": "courgette",
    "eieren": "ei",
    "kipfilets": "kipfilet",
    "kruidnagels": "kruidnagel",
    "chilipepers": "chilipeper",
    "limoenen": "limoen",
    "citroenen": "citroen",
    "perziken": "perzik",
    # look = knoflook (nl-BE)
    "knoflook": "look",
    # laurier-varianten
    "laurierblad": "laurier",
    "laurierblaadjes": "laurier",
    # peper: zwarte/witte/gemalen peper en molenvarianten vallen samen op "peper"
    "zwarte peper": "peper",
    "witte peper": "peper",
    "gemalen peper": "peper",
    "peper van de molen": "peper",
    # kruiden/specerijen-varianten
    "komijnpoeder": "komijn",
    "kaneelstokje": "kaneel",
    "kaneelstok": "kaneel",
    "chiliflakes": "chilivlokken",
    "peterseliestelen": "peterselie",
    "peterseliestengel": "peterselie",
}


def canonicalize_ingredient_name(name: str) -> str:
    """Strip toelichtingen tussen haakjes, pel voorvoegsels af en pas synoniemen toe.
    Nooit een lege string teruggeven."""
    without_parens = _PARENTHETICAL_RE.sub("", name).strip()
    words = (without_parens or name).split()
    start = 0
    while start < len(words) - 1:  # minstens één woord laten staan
        token = words[start].strip(".,").lower()
        if token in _STRIPPABLE:
            start += 1
            continue
        break
    stripped = " ".join(words[start:]).strip() or name.strip()
    return _SYNONYMS.get(stripped.lower(), stripped)


# --- Herb-detectie (voorraadtype "Kruiden") ---

# Losse woorden (genormaliseerd = lowercase). Match als de volledige naam hierin staat
# óf als één van z'n woorden hierin staat ("verse basilicum" → 'basilicum'). Bewust
# GEEN losse "peper" (botst met paprika/Spaanse peper); "peper" wordt via de synoniemen
# hierboven al de canonieke naam en staat expliciet in deze lijst.
HERB_TERMS: frozenset[str] = frozenset({
    # verse/gedroogde kruiden
    "basilicum", "peterselie", "bladpeterselie", "bieslook", "koriander",
    "korianderblad", "dille", "dragon", "kervel", "munt", "pepermunt", "oregano",
    "rozemarijn", "salie", "tijm", "laurier", "marjolein", "majoraan", "lavas",
    "citroenmelisse",
    # specerijen / gedroogde kruiden
    "peper", "kaneel", "nootmuskaat", "kruidnagel", "kurkuma", "komijn", "karwij",
    "karwijzaad", "kerrie", "kerriepoeder", "currypoeder", "kardemom", "venkelzaad",
    "mosterdzaad", "chilipoeder", "chilivlokken", "cayennepeper", "paprikapoeder",
    "saffraan", "steranijs", "anijs", "foelie", "piment", "sumak", "zaatar",
    "fenegriek", "korianderzaad", "knoflookpoeder", "lookpoeder", "uienpoeder",
    "selderijzout", "gemberpoeder", "vanille", "vijfkruidenpoeder", "kipkruiden",
    "harissa",
})

# Meerwoords-termen: match als de frase ergens in de naam voorkomt.
HERB_PHRASES: tuple[str, ...] = (
    "herbes de provence", "provencaalse kruiden", "italiaanse kruiden",
    "garam masala", "ras el hanout", "gedroogde kruiden",
    "gerookt paprikapoeder", "pul biber", "sharena sol",
)


def is_herb(name: str | None) -> bool:
    """True als de (bij voorkeur reeds gecanonicaliseerde) naam een kruid/specerij is."""
    if not name:
        return False
    text = name.strip().lower()
    if text in HERB_TERMS:
        return True
    if set(text.split()) & HERB_TERMS:
        return True
    return any(phrase in text for phrase in HERB_PHRASES)
