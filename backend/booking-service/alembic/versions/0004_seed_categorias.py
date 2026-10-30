"""dados iniciais: as tres categorias do complexo"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
        INSERT INTO categories (name, description) VALUES
          ('Coworking', 'Mesas e salas de reunião'),
          ('Estacionamento', 'Vagas de estacionamento'),
          ('Desporto', 'Ginásio com personal trainer e quadra de padel')
        ON CONFLICT (name) DO NOTHING
    """)

def downgrade() -> None:
    op.execute("""
        DELETE FROM categories
        WHERE name IN ('Coworking', 'Estacionamento', 'Desporto')
    """)