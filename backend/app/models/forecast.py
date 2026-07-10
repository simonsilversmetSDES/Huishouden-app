from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import AssetClass, str_enum


class ForecastFormula(Base):
    """Door de gebruiker aangepaste forecast-formule (Excel-werkblad "Status balans").

    year=0/month=0 is de rij-default voor een activaklasse; een concrete
    (year, month) is een cel-override die de rij-formule vervangt. Sentinel 0
    i.p.v. NULL omdat SQLite NULLs in een unique constraint als verschillend
    behandelt. Standaardformules staan hardcoded in de service; hier komen
    enkel afwijkingen terecht."""

    __tablename__ = "forecast_formulas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    context_id: Mapped[int] = mapped_column(ForeignKey("contexts.id"))
    asset_class: Mapped[AssetClass] = mapped_column(str_enum(AssetClass, "asset_class"))
    year: Mapped[int] = mapped_column(Integer, default=0)
    month: Mapped[int] = mapped_column(Integer, default=0)
    formula: Mapped[str] = mapped_column(String)

    __table_args__ = (
        UniqueConstraint("context_id", "asset_class", "year", "month"),
        CheckConstraint("month BETWEEN 0 AND 12", name="forecast_month_range"),
        CheckConstraint("(year = 0) = (month = 0)", name="forecast_default_sentinel"),
    )
