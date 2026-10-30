"""reservas: CHECK nos valores de status

A constraint contra sobreposição (reservations_no_overlap) só vale para
status IN ('HELD', 'CONFIRMED'). Sem este CHECK, um valor mal escrito
(ex.: 'confirmed' em minúsculas) passava ao lado da constraint e permitia
duas reservas no mesmo horário. Os scripts SQL antigos tinham este CHECK;
perdeu-se na passagem para o Alembic.
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "reservations_status_check",
        "reservations",
        "status IN ('HELD', 'CONFIRMED', 'CANCELLED')",
    )


def downgrade() -> None:
    op.drop_constraint("reservations_status_check", "reservations", type_="check")