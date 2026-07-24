"""recipe moments many to many

Revision ID: c7a1f4e9b2d3
Revises: 788b69c8db41
Create Date: 2026-07-24 10:00:00.000000

Zet ``recipes.moment_id`` (één moment per recept) om naar een many-to-many
koppeltabel ``recipe_moment_links`` — analoog aan de eerdere categorie-migratie
(835d05468274). Recepten met het moment "Beide" worden gesplitst in aparte links
naar "Lunch" én "Diner"; het moment "Beide" verdwijnt daarna.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.types  # custom types (MoneyCents, PreciseDecimal) in autogenerate


# revision identifiers, used by Alembic.
revision: str = 'c7a1f4e9b2d3'
down_revision: Union[str, Sequence[str], None] = '788b69c8db41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('recipe_moment_links',
    sa.Column('recipe_id', sa.Integer(), nullable=False),
    sa.Column('moment_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['moment_id'], ['recipe_moments.id'], name=op.f('fk_recipe_moment_links_moment_id_recipe_moments')),
    sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], name=op.f('fk_recipe_moment_links_recipe_id_recipes')),
    sa.PrimaryKeyConstraint('recipe_id', 'moment_id', name=op.f('pk_recipe_moment_links'))
    )

    bind = op.get_bind()

    def moment_id_by_name(name: str) -> int | None:
        return bind.execute(
            sa.text("SELECT id FROM recipe_moments WHERE name = :name"), {"name": name}
        ).scalar()

    # Match op de geseede namen. Zijn die hernoemd, dan splitst "Beide" niet
    # automatisch en blijft de bestaande koppeling behouden (defensieve terugval).
    beide_id = moment_id_by_name("Beide")
    lunch_id = moment_id_by_name("Lunch")
    diner_id = moment_id_by_name("Diner")

    if beide_id is None:
        # Geen "Beide": alle enkelvoudige momenten 1-op-1 overzetten.
        bind.execute(sa.text(
            "INSERT INTO recipe_moment_links (recipe_id, moment_id) "
            "SELECT id, moment_id FROM recipes WHERE moment_id IS NOT NULL"
        ))
    else:
        # Alles behalve "Beide" 1-op-1 overzetten...
        bind.execute(sa.text(
            "INSERT INTO recipe_moment_links (recipe_id, moment_id) "
            "SELECT id, moment_id FROM recipes "
            "WHERE moment_id IS NOT NULL AND moment_id != :beide_id"
        ), {"beide_id": beide_id})
        # ...en "Beide" opsplitsen in aparte links naar Lunch én Diner (voor
        # zover die momenten bestaan).
        for target_id in (lunch_id, diner_id):
            if target_id is not None:
                bind.execute(sa.text(
                    "INSERT INTO recipe_moment_links (recipe_id, moment_id) "
                    "SELECT id, :target_id FROM recipes WHERE moment_id = :beide_id"
                ), {"target_id": target_id, "beide_id": beide_id})
        # "Beide" verwijderen — de gebruiker wil dit moment weg.
        bind.execute(
            sa.text("DELETE FROM recipe_moments WHERE id = :beide_id"), {"beide_id": beide_id}
        )

    with op.batch_alter_table('recipes', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_recipes_moment_id_recipe_moments'), type_='foreignkey')
        batch_op.drop_column('moment_id')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('recipes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('moment_id', sa.INTEGER(), nullable=True))
        batch_op.create_foreign_key(batch_op.f('fk_recipes_moment_id_recipe_moments'), 'recipe_moments', ['moment_id'], ['id'])

    # Eén moment per recept terugzetten (laagste moment_id wint). Data-verlies bij
    # recepten met >1 moment is inherent; "Beide" wordt niet gereconstrueerd.
    op.execute(
        "UPDATE recipes SET moment_id = ("
        "SELECT MIN(moment_id) FROM recipe_moment_links "
        "WHERE recipe_moment_links.recipe_id = recipes.id"
        ")"
    )

    op.drop_table('recipe_moment_links')
