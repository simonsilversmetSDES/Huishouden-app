from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import AssetClass, str_enum
from app.types import MoneyCents


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    snapshot_date: Mapped[date] = mapped_column(Date)
    balance: Mapped[Decimal] = mapped_column(MoneyCents)

    __table_args__ = (UniqueConstraint("account_id", "snapshot_date"),)


class NetWorthSnapshot(Base):
    __tablename__ = "net_worth_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    context_id: Mapped[int] = mapped_column(ForeignKey("contexts.id"))
    snapshot_date: Mapped[date] = mapped_column(Date)
    asset_class: Mapped[AssetClass] = mapped_column(str_enum(AssetClass, "asset_class"))
    value: Mapped[Decimal] = mapped_column(MoneyCents)

    __table_args__ = (UniqueConstraint("context_id", "snapshot_date", "asset_class"),)
