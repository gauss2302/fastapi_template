# alembic/env.py - ПРАВИЛЬНАЯ ВЕРСИЯ ДЛЯ СИНХРОННОЙ РАБОТЫ
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Connection
from alembic import context

# Импортируем наши модели и конфигурацию
from app.core.config import settings
from app.core.database import Base

# Импортируем все модели чтобы Alembic их видел
from app.models.user import User
from app.models.company import Company
from app.models.recruiter import Recruiter

# this is the Alembic Config object
config = context.config

# Устанавливаем DATABASE_URL из нашей конфигурации
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_SYNC)

# add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    # Создаём обычный синхронный engine
    connectable = create_engine(
        settings.DATABASE_URL_SYNC,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()