import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, pool

load_dotenv()

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None

def get_url() -> str | URL:
    # Docker Compose: o contentor de migração recebe a URL inteira
    url = os.environ.get("BOOKING_DATABASE_URL")
    if url:
        return url
    # Kubernetes: o Job de migração tem as mesmas variáveis do serviço (DB_HOST,
    # DB_PASSWORD...), e a URL é montada pelo app/config.py, que trata dos
    # caracteres especiais na senha
    if os.environ.get("DB_PASSWORD"):
        from app.config import get_settings
        return get_settings().database_url
    raise RuntimeError("Defina BOOKING_DATABASE_URL ou DB_HOST e DB_PASSWORD (veja o .env).")

def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    engine = create_engine(get_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()