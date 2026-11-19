"""terminar sessões: session_version

Um JWT vale até expirar (30 min) e o auth não guarda as sessões. Para as terminar,
cada utilizador tem um número de versão, que vai dentro de cada token (claim "sv").
Quando a versão sobe, os tokens com a versão antiga deixam de valer no auth.

Sobe quando o utilizador troca a palavra-passe, quando o admin a redefine e quando o
admin repõe o 2FA. Começa em 0: os tokens emitidos antes desta migração (sem "sv")
contam como versão 0 e continuam a valer até expirarem.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "session_version")