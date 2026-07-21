"""Lineair herberekenen van ingrediënt-hoeveelheden bij een ander aantal personen.

Werkt op de quantity-strings die parsing.py opslaat (zie ``_INGREDIENT_RE`` aldaar):
een los getal ("500", "1,5"), een unicode-breuk ("½", "¼", "¾"), of twee getallen met
een scheidingsteken ("1/2", "2-3"). "/" betekent een breuk (1 gedeeld door 2, dus
schalen als decimaal); "-"/"–" betekent een range (bv. "2-3 tomaten") — beide kanten
apart schalen en weer samenvoegen. Niet-numerieke hoeveelheden ("snufje") blijven
ongewijzigd; die kunnen niet zinvol geschaald worden. Zelfde logica als
``frontend/src/weekmenu/servings.ts`` (client-side live-preview bij de stepper).
"""

import re

_UNICODE_FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75}
_FRACTION_RE = re.compile(r"^(.+?)\s*/\s*(.+)$")
_RANGE_RE = re.compile(r"^(.+?)\s*[-–]\s*(.+)$")


def _parse_number(token: str) -> float | None:
    if token in _UNICODE_FRACTIONS:
        return _UNICODE_FRACTIONS[token]
    try:
        return float(token.replace(",", "."))
    except ValueError:
        return None


def _format_number(value: float) -> str:
    rounded = round(value, 2)
    if rounded == int(rounded):
        rounded = int(rounded)
    return str(rounded).replace(".", ",")


def scale_quantity(quantity: str | None, factor: float) -> str | None:
    if quantity is None or factor == 1:
        return quantity
    trimmed = quantity.strip()

    fraction_match = _FRACTION_RE.match(trimmed)
    if fraction_match:
        numerator = _parse_number(fraction_match.group(1))
        denominator = _parse_number(fraction_match.group(2))
        if numerator is not None and denominator:
            return _format_number((numerator / denominator) * factor)

    range_match = _RANGE_RE.match(trimmed)
    if range_match:
        start = _parse_number(range_match.group(1))
        end = _parse_number(range_match.group(2))
        if start is not None and end is not None:
            return f"{_format_number(start * factor)}-{_format_number(end * factor)}"

    single = _parse_number(trimmed)
    if single is not None:
        return _format_number(single * factor)

    return quantity
