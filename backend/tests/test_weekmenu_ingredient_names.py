"""Canonicalisatie van ingrediëntnamen (voorvoegsels weg + synoniemen) en herb-detectie."""

import pytest

from app.weekmenu.ingredient_names import canonicalize_ingredient_name, is_herb


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # maatwoorden/porties weg
        ("enkele takjes munt", "munt"),
        ("takje tijm", "tijm"),
        ("bolletje zwarte peper", "peper"),  # + synoniem zwarte peper → peper
        ("dopje witte wijn", "witte wijn"),  # kleur BLIJFT (ander product)
        ("scheut Rode wijnazijn", "Rode wijnazijn"),
        # versheid/grootte weg
        ("verse munt", "munt"),
        ("dikke wortelen", "wortelen"),
        ("kleine courgettes", "courgette"),  # + meervoud-synoniem
        # merk weg
        ("Boni olijfolie", "olijfolie"),
        ("Spar jonge sla", "jonge sla"),
        # 'gemalen' + connector-leftover
        ("kl gemalen komijn", "komijn"),
        ("mix van kerstomaatjes", "kerstomaatjes"),
        # haakjes weg
        ("toefje Harissa (naar smaak)", "Harissa"),
        ("tomatenpulp (blik)", "tomatenpulp"),
        # enkelvoud/meervoud- en semantische synoniemen
        ("uien", "ui"),
        ("Wortel", "wortelen"),
        ("wortels", "wortelen"),
        ("knoflook", "look"),
        ("laurierblad", "laurier"),
        ("peper van de molen", "peper"),
        # niets te strippen
        ("olijfolie", "olijfolie"),
        ("rode ui", "rode ui"),  # kleur blijft
    ],
)
def test_canonicalize(raw: str, expected: str) -> None:
    assert canonicalize_ingredient_name(raw) == expected


def test_canonicalize_nooit_leeg() -> None:
    # Enkel maatwoorden → laatste woord blijft staan (nooit lege naam).
    assert canonicalize_ingredient_name("snufje") == "snufje"


@pytest.mark.parametrize(
    "name", ["munt", "peper", "basilicum", "tijm", "laurier", "komijn", "lookpoeder"]
)
def test_is_herb_true(name: str) -> None:
    assert is_herb(name) is True


@pytest.mark.parametrize("name", ["ui", "look", "wortelen", "chilipeper", "kipfilet", "paprika"])
def test_is_herb_false(name: str) -> None:
    assert is_herb(name) is False
