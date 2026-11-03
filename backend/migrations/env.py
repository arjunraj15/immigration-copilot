"""Alembic environment. The database URL comes from app settings, never from alembic.ini.
Migrations run as the database owner, not as the limited app role."""

from alembic import context
from sqlalchemy import create_engine

from app.core.config import get_settings

# Import your model modules here so autogenerate can see them. Set target_metadata
# to the shared Base.metadata once models exist.
target_metadata = None


def run_migrations_online() -> None:
    engine = create_engine(get_settings().migration_database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
