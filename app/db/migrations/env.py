import os
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool
from dotenv import load_dotenv

# Add the app directory to sys.path so 'db', 'queues', etc. can be imported
app_dir = str(Path(__file__).resolve().parent.parent.parent)
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

# Load .env from the app directory
load_dotenv(dotenv_path=Path(app_dir) / ".env")

from db.base import Base
from db.models import *  # noqa: F401,F403 - register all models with metadata

target_metadata = Base.metadata


def get_database_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    return url


def run_migrations_offline():
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = create_engine(
        get_database_url(),
        poolclass=pool.NullPool,
    )

    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
