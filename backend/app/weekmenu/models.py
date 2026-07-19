"""SQLAlchemy-modellen voor Weekmenu (tabellen volgen in Fase 1).

De modellen gebruiken de gedeelde ``Base`` (zelfde metadata + naming conventions
als Financiën), zodat Alembic-autogenerate en de test-``create_all`` in
``tests/conftest.py`` ze zien. Let op voor Fase 1: importeer deze module in
``app/models/__init__.py`` zodra hier tabellen staan, anders blijft
``Base.metadata`` onvolledig.
"""

from app.models.base import Base as Base
