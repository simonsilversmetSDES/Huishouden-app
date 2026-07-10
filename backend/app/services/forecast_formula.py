"""Mini-formule-DSL voor de vermogensforecast (Excel-werkblad "Status balans").

Ondersteunt: + - * /, haakjes, unaire min, getallen (punt óf komma als
decimaalteken), variabelen `vorige` en `kapitaalaflossing`, en de functie
`budget("Categorienaam")`. Recursive-descent parser, rekenen in Decimal,
geen eval. Een onbestaande budgetcategorie breekt de keten niet: waarde 0
plus een warning (spec-gedrag: Excel telt een lege cel ook als 0).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, DivisionByZero, InvalidOperation

MAX_FORMULA_LENGTH = 500

ZERO = Decimal("0")

VARIABLES = ("vorige", "kapitaalaflossing")
FUNCTIONS = ("budget",)


class FormulaError(ValueError):
    """Fout in een forecast-formule, met positie (0-gebaseerd) in de tekst."""

    def __init__(self, message: str, position: int) -> None:
        super().__init__(message)
        self.position = position


@dataclass
class EvalContext:
    """Waarden voor één (context, maand)-evaluatie.

    `budget_lookup` geeft None terug voor een onbekende categorie; de
    evaluator vertaalt dat naar 0 + warning.
    """

    vorige: Decimal
    kapitaalaflossing: Decimal
    budget_lookup: Callable[[str], Decimal | None]
    warnings: list[str] = field(default_factory=list)


# --- tokenizer -------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<number>\d+(?:[.,]\d+)?)
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<string>"[^"]*"|'[^']*')
  | (?P<op>[+\-*/()])
    """,
    re.VERBOSE,
)


@dataclass
class _Token:
    kind: str  # number | ident | string | op | end
    text: str
    position: int


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if match is None:
            raise FormulaError(f"Onverwacht teken '{text[pos]}'", pos)
        kind = match.lastgroup
        assert kind is not None
        if kind != "ws":
            tokens.append(_Token(kind, match.group(), match.start()))
        pos = match.end()
    tokens.append(_Token("end", "", len(text)))
    return tokens


# --- AST -------------------------------------------------------------------


@dataclass
class _Number:
    value: Decimal


@dataclass
class _Variable:
    name: str


@dataclass
class _BudgetCall:
    category: str


@dataclass
class _Unary:
    op: str
    operand: _Node


@dataclass
class _Binary:
    op: str
    left: _Node
    right: _Node
    position: int  # voor "deling door nul"-meldingen


_Node = _Number | _Variable | _BudgetCall | _Unary | _Binary


# --- parser ----------------------------------------------------------------


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self.tokens = tokens
        self.index = 0

    @property
    def current(self) -> _Token:
        return self.tokens[self.index]

    def advance(self) -> _Token:
        token = self.current
        self.index += 1
        return token

    def expect_op(self, op: str) -> None:
        if self.current.kind == "op" and self.current.text == op:
            self.advance()
            return
        raise FormulaError(f"'{op}' verwacht", self.current.position)

    def parse(self) -> _Node:
        node = self.expression()
        if self.current.kind != "end":
            raise FormulaError(
                f"Onverwachte invoer '{self.current.text}' na de expressie",
                self.current.position,
            )
        return node

    def expression(self) -> _Node:
        node = self.term()
        while self.current.kind == "op" and self.current.text in "+-":
            op = self.advance()
            node = _Binary(op.text, node, self.term(), op.position)
        return node

    def term(self) -> _Node:
        node = self.factor()
        while self.current.kind == "op" and self.current.text in "*/":
            op = self.advance()
            node = _Binary(op.text, node, self.factor(), op.position)
        return node

    def factor(self) -> _Node:
        token = self.current
        if token.kind == "op" and token.text in "+-":
            self.advance()
            return _Unary(token.text, self.factor())
        return self.primary()

    def primary(self) -> _Node:
        token = self.current
        if token.kind == "number":
            self.advance()
            try:
                return _Number(Decimal(token.text.replace(",", ".")))
            except InvalidOperation:  # pragma: no cover — regex sluit dit al uit
                raise FormulaError(f"Ongeldig getal '{token.text}'", token.position) from None
        if token.kind == "ident":
            self.advance()
            if token.text in VARIABLES:
                return _Variable(token.text)
            if token.text in FUNCTIONS:
                self.expect_op("(")
                arg = self.current
                if arg.kind != "string":
                    raise FormulaError(
                        'budget(...) verwacht een categorienaam tussen quotes, '
                        'bv. budget("Spaarrekening")',
                        arg.position,
                    )
                self.advance()
                self.expect_op(")")
                return _BudgetCall(arg.text[1:-1])
            raise FormulaError(
                f"Onbekende naam '{token.text}' — beschikbaar: "
                f"{', '.join(VARIABLES)} en budget(\"...\")",
                token.position,
            )
        if token.kind == "op" and token.text == "(":
            self.advance()
            node = self.expression()
            self.expect_op(")")
            return node
        raise FormulaError("Getal, variabele of '(' verwacht", token.position)


def _parse(text: str) -> _Node:
    if len(text) > MAX_FORMULA_LENGTH:
        raise FormulaError(f"Formule te lang (max {MAX_FORMULA_LENGTH} tekens)", 0)
    if text.strip() == "":
        raise FormulaError("Lege formule", 0)
    return _Parser(_tokenize(text)).parse()


def validate_formula(text: str) -> None:
    """Controleer syntax en namen zonder te evalueren (voor de PUT-route)."""
    _parse(text)


# --- evaluator ---------------------------------------------------------------


def _eval(node: _Node, ctx: EvalContext) -> Decimal:
    match node:
        case _Number(value):
            return value
        case _Variable(name):
            return ctx.vorige if name == "vorige" else ctx.kapitaalaflossing
        case _BudgetCall(category):
            value = ctx.budget_lookup(category)
            if value is None:
                warning = f"Budgetcategorie '{category}' bestaat niet — telt als € 0"
                if warning not in ctx.warnings:
                    ctx.warnings.append(warning)
                return ZERO
            return value
        case _Unary(op, operand):
            value = _eval(operand, ctx)
            return -value if op == "-" else value
        case _Binary(op, left, right, position):
            lhs = _eval(left, ctx)
            rhs = _eval(right, ctx)
            if op == "+":
                return lhs + rhs
            if op == "-":
                return lhs - rhs
            if op == "*":
                return lhs * rhs
            try:
                return lhs / rhs
            except (DivisionByZero, InvalidOperation):
                raise FormulaError("Deling door nul", position) from None
    raise AssertionError(f"Onbekend AST-knooptype: {node!r}")  # pragma: no cover


def evaluate_formula(text: str, ctx: EvalContext) -> Decimal:
    """Parse en evalueer een formule voor één maand; FormulaError bij fouten."""
    return _eval(_parse(text), ctx)
