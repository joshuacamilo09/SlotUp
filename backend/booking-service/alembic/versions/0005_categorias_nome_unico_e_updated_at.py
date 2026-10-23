"""categorias: nome único sem diferenciar maiúsculas e coluna updated_at

- "Coworking" e "coworking" passam a contar como a mesma categoria.
  O índice único sobre lower(name) é a garantia final: mesmo com dois admins
  a criar a mesma categoria ao mesmo tempo, em réplicas diferentes, só um consegue.
- updated_at regista a última edição (o PATCH do admin).
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "categories",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.drop_constraint("categories_name_key", "categories", type_="unique")
    op.create_index("categories_name_lower_key", "categories",
                    [sa.text("lower(name)")], unique=True)


def downgrade() -> None:
    op.drop_index("categories_name_lower_key", table_name="categories")
    op.create_unique_constraint("categories_name_key", "categories", ["name"])
    op.drop_column("categories", "updated_at")