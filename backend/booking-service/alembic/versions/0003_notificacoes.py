"""notificacoes (outbox de emails)"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_email", sa.String(255), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("reservations.id")),
        sa.Column("waitlist_entry_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("waitlist_entries.id")),
        sa.Column("payload", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(10), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "type IN ('RESERVATION_CREATED', 'RESERVATION_CANCELLED', "
            "'WAITLIST_JOINED', 'WAITLIST_OFFERED')",
            name="notifications_type_check"),
        sa.CheckConstraint("status IN ('PENDING', 'SENT', 'FAILED')",
                           name="notifications_status_check"),
        sa.CheckConstraint("attempts >= 0", name="notifications_attempts_check"),
        sa.CheckConstraint("reservation_id IS NOT NULL OR waitlist_entry_id IS NOT NULL",
                           name="notifications_has_reference"),
        sa.CheckConstraint("(status = 'SENT') = (sent_at IS NOT NULL)",
                           name="notifications_sent_has_date"),
    )

    op.create_index("notifications_pending_idx", "notifications", ["next_attempt_at"],
                    postgresql_where=sa.text("status = 'PENDING'"))
    op.create_index("notifications_once_per_reservation", "notifications",
                    ["type", "reservation_id"], unique=True,
                    postgresql_where=sa.text("waitlist_entry_id IS NULL"))
    op.create_index("notifications_once_per_waitlist_entry", "notifications",
                    ["type", "waitlist_entry_id"], unique=True,
                    postgresql_where=sa.text("waitlist_entry_id IS NOT NULL"))

def downgrade() -> None:
    op.drop_table("notifications")