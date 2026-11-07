"""tokens de redefinição de palavra-passe

O admin pede a redefinição e o auth gera um token aleatório de uso único.
Na tabela fica só o hash SHA-256 do token (nunca o token em si): quem ler a
base de dados não consegue usar os tokens.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        # Se o utilizador for apagado, os tokens dele vão junto
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),  # SHA-256 em hexadecimal
        # O admin que pediu (auditoria); se esse admin for apagado, fica NULL
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("token_hash", name="password_reset_tokens_hash_key"),
        sa.CheckConstraint("expires_at > created_at", name="password_reset_tokens_expiry_check"),
    )
    # No máximo um token por usar por utilizador (mesmo com dois admins em réplicas diferentes)
    op.create_index("password_reset_tokens_one_active", "password_reset_tokens", ["user_id"],
                    unique=True, postgresql_where=sa.text("used_at IS NULL"))


def downgrade() -> None:
    op.drop_index("password_reset_tokens_one_active", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")