"""security.soort: soort belegging (etf_fondsen/aandelen/bitcoin) voor de vermogensbalans (spec §9)

Nieuwe activaklassen/rekening-types (bitcoin, pensioensparen, groepsverzekering) vergen
géén DB-wijziging: die enums zijn VARCHAR zonder CHECK (validatie gebeurt Python-zijdig),
en SQLite negeert de kolomlengte. Enkel de nieuwe kolom `securities.soort` is een echte
schemawijziging.

Revision ID: d8b3f0a7c1e2
Revises: c3d5a9f21e77
Create Date: 2026-07-08 09:00:00.000000
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8b3f0a7c1e2"
down_revision: Union[str, Sequence[str], None] = "c3d5a9f21e77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bestaande effecten krijgen 'etf_fondsen'; aandelen/bitcoin zet de gebruiker nadien
    # in de beleggingen-tab.
    op.add_column(
        "securities",
        sa.Column("soort", sa.String(), nullable=False, server_default="etf_fondsen"),
    )


def downgrade() -> None:
    with op.batch_alter_table("securities") as batch_op:
        batch_op.drop_column("soort")
