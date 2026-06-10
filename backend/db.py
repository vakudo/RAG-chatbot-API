import psycopg

from backend.config import settings


def connect() -> psycopg.Connection:
    """Plain psycopg connection from the SQLAlchemy-style PG_CONN setting."""
    dsn = settings.pg_conn.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(dsn)
