"""Alembic environment — reads DATABASE_URL from settings, supports async pg driver."""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Make the project root importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Load all models so Alembic can see the metadata
from db.models import Base  # noqa: F401
from db.models_appbuilder import Base as AppBase  # noqa: F401
from db.models_marketplace import Base as MktBase  # noqa: F401
from db.models_pattern_rules import Base as RulesBase  # noqa: F401

config = context.config

# Override sqlalchemy.url from env if DATABASE_URL is set
_db_url = os.getenv("DATABASE_URL", "")
if _db_url:
    # Convert async drivers to sync equivalents for alembic
    sync_url = _db_url \
        .replace("postgresql+asyncpg://", "postgresql+psycopg2://") \
        .replace("sqlite+aiosqlite://",   "sqlite://")
    config.set_main_option("sqlalchemy.url", sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use merged metadata from all model files
from sqlalchemy import MetaData
target_metadata = Base.metadata
# Merge other metadata tables into Base.metadata so autogenerate sees them
for b in (AppBase, MktBase, RulesBase):
    for table in b.metadata.tables.values():
        if table.name not in target_metadata.tables:
            table.tometadata(target_metadata)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generate SQL without a live DB)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
