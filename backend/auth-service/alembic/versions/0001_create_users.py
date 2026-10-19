"""create users"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", sa.String(10), nullable=False, server_default="USER"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("two_fa_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("totp_secret_encrypted", postgresql.BYTEA),
        sa.Column("totp_last_used_step", sa.BigInteger),
        sa.Column("failed_login_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('ADMIN', 'USER')", name="users_role_check"),
        sa.CheckConstraint("failed_login_attempts >= 0", 
                           name="users_failed_login_attempts_check"),
        sa.CheckConstraint("NOT two_fa_enabled OR totp_secret_encrypted IS NOT NULL",
                           name="users_2fa_requires_secret"),
    )
    #email único sem diferenciar maiúsculas de minúsculas
    op.create_index("users_email_lower_key", "users", 
                    [sa.text("lower(email)")], unique=True)

def downgrade() -> None:
    op.drop_index("users_email_lower_key", table_name="users")
    op.drop_table("users")