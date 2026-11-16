"""Alembic environment. Run through app.migrate.migrate(), which passes its own connection."""
from alembic import context
from sqlalchemy import create_engine

from app import models  # noqa: F401  (register tables)
from app.config import get_settings
from app.db import Base


def run(connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata,
                      render_as_batch=connection.dialect.name == "sqlite", compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


conn = context.config.attributes.get("connection")
if conn is not None:
    run(conn)
else:
    with create_engine(get_settings().database_url).connect() as c:
        run(c)
        c.commit()
