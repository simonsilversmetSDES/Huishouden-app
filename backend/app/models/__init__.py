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
from app.models.month_note import MonthNote
from app.models.snapshots import AccountSnapshot, NetWorthSnapshot
from app.models.transactions import CategorizationRule, Import, RuleContext, Transaction

# Weekmenu-feature (app/weekmenu/): import zodat Base.metadata compleet is voor
# Alembic-autogenerate en de test-create_all. Bewust niet in __all__ — weekmenu-code
# importeert zijn modellen rechtstreeks uit app.weekmenu.models.
from app.weekmenu import models as _weekmenu_models  # noqa: E402,F401

__all__ = [
    "Base",
    "User",
    "Context",
    "Account",
    "Category",
    "Budget",
    "BudgetNote",
    "MonthNote",
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
