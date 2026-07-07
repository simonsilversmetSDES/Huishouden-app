from pydantic import BaseModel, ConfigDict

from app.models.enums import AccountType, Bank, CategoryType


class ContextOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: AccountType


class AccountIn(BaseModel):
    context_id: int
    name: str
    type: AccountType = AccountType.ANDERE
    bank: Bank = Bank.ANDERE
    iban: str | None = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: CategoryType


class CategoryIn(BaseModel):
    context_id: int
    name: str
    type: CategoryType
