"""rule_contexts-cleanup: koppelingen verwijderen waar de categorie niet (actief) bestaat

Een regel kan enkel gelden voor een entiteit die een ACTIEVE categorie met
dezelfde naam heeft (de engine lost de categorie per entiteit op naam op; anders
wordt de regel daar stil overgeslagen). Bestaande koppelingen naar entiteiten
zonder die categorie — bv. BAKKERIJ→Boodschappen gekoppeld aan Simon/Jozefien
terwijl 'Boodschappen' daar inactief is — worden opgeruimd.

Revision ID: c9d2e5f4a3b7
Revises: b4e8d6c3f2a1
Create Date: 2026-07-09 09:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

revision: str = "c9d2e5f4a3b7"
down_revision: str | Sequence[str] | None = "b4e8d6c3f2a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM rule_contexts
        WHERE NOT EXISTS (
            SELECT 1
            FROM categorization_rules r
            JOIN categories rc ON rc.id = r.category_id
            JOIN categories c
              ON c.context_id = rule_contexts.context_id
             AND c.name = rc.name
             AND c.active = 1
            WHERE r.id = rule_contexts.rule_id
        )
        """
    )


def downgrade() -> None:
    # Datacleanup — de verwijderde (ongeldige) koppelingen zijn niet reconstrueerbaar.
    pass
