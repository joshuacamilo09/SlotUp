"""catalogo: categorias, recursos e regras de disponibilidade"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("name", name="categories_name_key"),
    )

    op.create_table(
        "resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("category_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("resource_type", sa.String(30), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("capacity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("attributes", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("capacity > 0", name="resources_capacity_check"),
        sa.UniqueConstraint("category_id", "name", name="resources_category_id_name_key"),
    )

    op.create_table(
        "availability_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("resources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weekday", sa.SmallInteger, nullable=False),
        sa.Column("open_time", sa.Time, nullable=False),
        sa.Column("close_time", sa.Time, nullable=False),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="availability_rules_weekday_check"),
        sa.CheckConstraint("close_time > open_time", name="availability_rules_check"),
        sa.UniqueConstraint("resource_id", "weekday", "open_time",
                            name="availability_rules_resource_id_weekday_open_time_key"),
    )

    op.create_index("resources_category_idx", "resources", ["category_id"])

def downgrade() -> None:
    op.drop_index("resources_category_idx", table_name="resources")
    op.drop_table("availability_rules")
    op.drop_table("resources")
    op.drop_table("categories")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")