"""Lineaire schaling van ingrediënt-hoeveelheden bij een ander aantal personen."""

import pytest

from app.weekmenu.servings import scale_quantity


@pytest.mark.parametrize(
    ("quantity", "factor", "expected"),
    [
        (None, 2, None),
        ("500", 1, "500"),
        ("500", 1.5, "750"),
        ("1,5", 2, "3"),
        ("1", 0.5, "0,5"),
        ("½", 2, "1"),
        ("¼", 4, "1"),
        ("1/2", 2, "1"),
        ("1/2", 1, "1/2"),
        ("2-3", 2, "4-6"),
        ("2–3", 1.5, "3-4,5"),
        ("snufje", 2, "snufje"),
    ],
)
def test_scale_quantity(quantity: str | None, factor: float, expected: str | None) -> None:
    assert scale_quantity(quantity, factor) == expected
