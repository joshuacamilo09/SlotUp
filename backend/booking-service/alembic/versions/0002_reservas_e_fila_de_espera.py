"""reservas e fila de espera"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_email", sa.String(255), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("resources.id"), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="CONFIRMED"),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status <> 'HELD' OR hold_expires_at IS NOT NULL",
                           name="reservations_held_has_deadline"),
        sa.CheckConstraint("end_at > start_at", name="reservations_valid_interval"),
        sa.CheckConstraint("(status = 'CANCELLED') = (cancelled_at IS NOT NULL)",
                           name="reservations_cancelled_has_date"),
    )

    op.execute("""
        ALTER TABLE reservations
        ADD CONSTRAINT reservations_no_overlap
        EXCLUDE USING gist (
            resource_id WITH =,
            tstzrange(start_at, end_at) WITH &&
        ) WHERE (status IN ('HELD', 'CONFIRMED'))
    """)

    op.create_index("reservations_user_idx", "reservations", ["user_id", "start_at"])
    op.create_index("reservations_hold_expiry_idx", "reservations", ["hold_expires_at"],
                    postgresql_where=sa.text("status = 'HELD'"))

    op.create_table(
        "waitlist_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_email", sa.String(255), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("resources.id"), nullable=False),
        sa.Column("desired_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("desired_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="WAITING"),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("reservations.id")),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('WAITING','OFFERED','ACCEPTED','EXPIRED','CANCELLED')",
            name="waitlist_entries_status_check"),
        sa.CheckConstraint("desired_end > desired_start", name="waitlist_valid_interval"),
        sa.CheckConstraint("status NOT IN ('OFFERED', 'ACCEPTED') OR reservation_id IS NOT NULL",
                           name="waitlist_offer_has_reservation"),
    )

    op.create_index("waitlist_queue_idx", "waitlist_entries", ["resource_id", "created_at"],
                    postgresql_where=sa.text("status = 'WAITING'"))
    op.create_index("waitlist_one_active_per_slot", "waitlist_entries",
                    ["user_id", "resource_id", "desired_start", "desired_end"],
                    unique=True,
                    postgresql_where=sa.text("status IN ('WAITING','OFFERED')"))

def downgrade() -> None:
    op.drop_table("waitlist_entries")
    op.drop_table("reservations")