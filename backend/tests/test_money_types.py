"""Tests voor de geld-TypeDecorators — geschreven vóór de implementatie (CLAUDE.md).

Geld wordt intern opgeslagen als integer-centen (MoneyCents) of als exacte
Decimal-tekst (PreciseDecimal). Floats zijn overal verboden.
"""

from decimal import Decimal

import pytest
from sqlalchemy import Integer, String, create_engine, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.models.base import Base
from app.types import MoneyCents, PreciseDecimal


class MoneyRow(Base):
    __tablename__ = "_test_money"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    amount: Mapped[Decimal] = mapped_column(MoneyCents)


class PreciseRow(Base):
    __tablename__ = "_test_precise"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[Decimal] = mapped_column(PreciseDecimal)
    label: Mapped[str] = mapped_column(String, default="")


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def roundtrip_money(session: Session, value: Decimal) -> Decimal:
    session.add(MoneyRow(amount=value))
    session.commit()
    session.expunge_all()
    return session.execute(
        select(MoneyRow.amount).order_by(MoneyRow.id.desc()).limit(1)
    ).scalar_one()


class TestMoneyCents:
    @pytest.mark.parametrize(
        "value",
        [
            Decimal("0.00"),
            Decimal("1234.56"),
            Decimal("-0.01"),
            Decimal("245000.00"),  # leningbedrag uit spec §8
            Decimal("1631.52"),  # maandlast uit spec §8
            Decimal("-99999999.99"),
            Decimal("99999999.99"),
        ],
    )
    def test_roundtrip_exact(self, session: Session, value: Decimal) -> None:
        assert roundtrip_money(session, value) == value

    def test_stored_as_integer_cents(self, session: Session) -> None:
        session.add(MoneyRow(amount=Decimal("12.34")))
        session.commit()
        raw = session.connection().exec_driver_sql("SELECT amount FROM _test_money").scalar_one()
        assert raw == 1234
        assert isinstance(raw, int)

    def test_returns_decimal_with_two_places(self, session: Session) -> None:
        result = roundtrip_money(session, Decimal("5"))
        assert isinstance(result, Decimal)
        assert result == Decimal("5.00")

    def test_rejects_float(self, session: Session) -> None:
        session.add(MoneyRow(amount=12.34))  # type: ignore[arg-type]
        with pytest.raises(Exception, match="float"):
            session.commit()

    def test_rejects_more_than_two_decimals(self, session: Session) -> None:
        session.add(MoneyRow(amount=Decimal("1.001")))
        with pytest.raises(Exception, match="centen"):
            session.commit()

    def test_accepts_int_and_str(self, session: Session) -> None:
        assert roundtrip_money(session, 5) == Decimal("5.00")  # type: ignore[arg-type]
        assert roundtrip_money(session, "7.25") == Decimal("7.25")  # type: ignore[arg-type]

    def test_none_allowed(self, session: Session) -> None:
        # Nullable kolommen (bv. fee/tax) moeten None kunnen bewaren.
        row = MoneyRow(amount=Decimal("1.00"))
        session.add(row)
        session.commit()
        assert MoneyCents().process_bind_param(None, None) is None
        assert MoneyCents().process_result_value(None, None) is None


class TestPreciseDecimal:
    @pytest.mark.parametrize(
        "value",
        [
            Decimal("0.013013"),  # fractionele BTC uit spec §7
            Decimal("98.240055"),  # gemiddelde aankoopprijs uit spec §10
            Decimal("25"),
            Decimal("-1.5"),
            Decimal("2456.00"),
        ],
    )
    def test_roundtrip_exact(self, session: Session, value: Decimal) -> None:
        session.add(PreciseRow(value=value))
        session.commit()
        session.expunge_all()
        stored = session.execute(
            select(PreciseRow.value).order_by(PreciseRow.id.desc())
        ).scalar_one()
        assert stored == value
        assert isinstance(stored, Decimal)

    def test_stored_as_text(self, session: Session) -> None:
        session.add(PreciseRow(value=Decimal("0.013013")))
        session.commit()
        raw = session.connection().exec_driver_sql("SELECT value FROM _test_precise").scalar_one()
        assert isinstance(raw, str)
        assert Decimal(raw) == Decimal("0.013013")

    def test_rejects_float(self, session: Session) -> None:
        session.add(PreciseRow(value=0.013013))  # type: ignore[arg-type]
        with pytest.raises(Exception, match="float"):
            session.commit()
