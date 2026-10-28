import os
from contextlib import contextmanager

import psycopg

APP_ENV = os.getenv("APP_ENV", "development").lower()
_configured_database_url = os.getenv("DATABASE_URL")

if APP_ENV == "production" and not _configured_database_url:
    raise RuntimeError("Production requires DATABASE_URL to be explicitly configured")

DATABASE_URL = _configured_database_url or "postgresql://postgres:postgres@localhost:5432/logistics"


@contextmanager
def get_connection():
    connection = psycopg.connect(DATABASE_URL)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
