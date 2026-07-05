from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import AccountType, Bank, CategoryType, str_enum


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)


class Context(Base):
    __tablename__ = "contexts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)

    accounts: Mapped[list["Account"]] = relationship(back_populates="context")
    categories: Mapped[list["Category"]] = relationship(back_populates="context")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    context_id: Mapped[int] = mapped_column(ForeignKey("contexts.id"))
    name: Mapped[str] = mapped_column(String)
    iban: Mapped[str | None] = mapped_column(String)
    bank: Mapped[Bank] = mapped_column(str_enum(Bank, "bank"))
    type: Mapped[AccountType] = mapped_column(str_enum(AccountType, "account_type"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    context: Mapped[Context] = relationship(back_populates="accounts")

    __table_args__ = (UniqueConstraint("context_id", "name"),)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    context_id: Mapped[int] = mapped_column(ForeignKey("contexts.id"))
    name: Mapped[str] = mapped_column(String)
    type: Mapped[CategoryType] = mapped_column(str_enum(CategoryType, "category_type"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    context: Mapped[Context] = relationship(back_populates="categories")

    __table_args__ = (UniqueConstraint("context_id", "type", "name"),)
