"""Alembic environment: run revisions online, one transaction per revision."""

from alembic import context
from sqlalchemy import create_engine, pool, text

config = context.config
engine = create_engine(config.attributes["database_url"], poolclass=pool.NullPool)

with engine.connect() as connection:
    # Fail fast rather than queue behind live traffic while holding DDL locks.
    connection.execute(text("SET lock_timeout = '10s'"))
    connection.commit()
    context.configure(connection=connection, transaction_per_migration=True)
    with context.begin_transaction():
        context.run_migrations()
