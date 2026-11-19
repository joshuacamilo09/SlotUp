"""recursos: duração mínima, máxima e intervalo entre reservas

Até aqui o scheduling (CSP) tinha estes valores fixos por tipo de recurso.
Agora cada recurso guarda os seus, o admin altera-os, e o booking envia-os
ao scheduling junto com o pedido.
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default: os recursos que já existem recebem este valor ao criar a coluna,
    # e um INSERT que não indique a coluna também
    op.add_column("resources", sa.Column("min_duration_min", sa.Integer(), nullable=False, server_default="15"))
    op.add_column("resources", sa.Column("max_duration_min", sa.Integer(), nullable=False, server_default="240"))
    op.add_column("resources", sa.Column("buffer_min", sa.Integer(), nullable=False, server_default="10"))

    # Valores iniciais dos recursos que já existem: os mesmos que o CSP tinha fixos por tipo.
    # Daqui em diante é o admin quem os muda, recurso a recurso.
    op.execute("UPDATE resources SET max_duration_min = 720 WHERE resource_type = 'mesa'")
    op.execute("UPDATE resources SET min_duration_min = 60, max_duration_min = 90 WHERE resource_type = 'quadra'")
    op.execute("UPDATE resources SET min_duration_min = 60, max_duration_min = 60 WHERE resource_type = 'personal'")
    # Vagas: até 24 h e sem intervalo de limpeza entre carros
    op.execute("UPDATE resources SET max_duration_min = 1440, buffer_min = 0 WHERE resource_type LIKE 'vaga%'")

    # Quem garante valores coerentes é o PostgreSQL, como nas outras tabelas.
    # % é o resto da divisão: % 15 = 0 quer dizer múltiplo de 15
    op.create_check_constraint(
        "resources_duration_check",
        "resources",
        "min_duration_min >= 15 AND min_duration_min % 15 = 0"
        " AND max_duration_min % 15 = 0 AND max_duration_min >= min_duration_min"
        " AND max_duration_min <= 1440",
    )
    op.create_check_constraint("resources_buffer_check", "resources", "buffer_min BETWEEN 0 AND 60")


def downgrade() -> None:
    op.drop_constraint("resources_buffer_check", "resources", type_="check")
    op.drop_constraint("resources_duration_check", "resources", type_="check")
    op.drop_column("resources", "buffer_min")
    op.drop_column("resources", "max_duration_min")
    op.drop_column("resources", "min_duration_min")