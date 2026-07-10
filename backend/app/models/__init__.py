"""Alle modellen importeren zodat Base.metadata compleet is (Alembic autogenerate)."""

from app.models.base import Base
from app.models.budget import Budget, BudgetNote
from app.models.core import Account, Category, Context, User
from app.models.forecast import ForecastFormula, ForecastNote
from app.models.investments import (
    Security,
    SecurityPrice,
    SecuritySplit,
    SecurityTransaction,
)
from app.models.loans import Loan, LoanContribution, LoanPayment, PropertyInvestment
from app.models.snapshots import AccountSnapshot, NetWorthSnapshot
from app.models.transactions import CategorizationRule, Import, RuleContext, Transaction

__all__ = [
    "Base",
    "User",
    "Context",
    "Account",
    "Category",
    "Budget",
    "BudgetNote",
    "ForecastFormula",
    "ForecastNote",
    "Transaction",
    "Import",
    "CategorizationRule",
    "RuleContext",
    "AccountSnapshot",
    "NetWorthSnapshot",
    "Security",
    "SecurityTransaction",
    "SecurityPrice",
    "SecuritySplit",
    "Loan",
    "LoanPayment",
    "PropertyInvestment",
    "LoanContribution",
]
