"""rule_contexts: op welke entiteiten een categorisatieregel geldt (spec §5.3, #9)

Koppeltabel (rule_id, context_id). Bestaande regels worden gebackfilld naar hun eigen
context_id, zodat de 'geldt voor'-set in de UI meteen klopt.

Revision ID: f2a9c4e6b8d1
Revises: d8b3f0a7c1e2
Create Date: 2026-07-08 10:00:00.000000
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2a9c4e6b8d1"
down_revision: Union[str, Sequence[str], None] = "d8b3f0a7c1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rule_contexts",
        sa.Column(
            "rule_id",
            sa.Integer(),
            sa.ForeignKey("categorization_rules.id"),
            primary_key=True,
        ),
        sa.Column(
            "context_id",
            sa.Integer(),
            sa.ForeignKey("contexts.id"),
            primary_key=True,
        ),
    )
    # Backfill: elke bestaande regel geldt (voorlopig) voor zijn eigen context.
    op.execute(
        "INSERT INTO rule_contexts (rule_id, context_id) "
        "SELECT id, context_id FROM categorization_rules"
    )


def downgrade() -> None:
    op.drop_table("rule_contexts")
