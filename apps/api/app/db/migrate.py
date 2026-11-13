"""Transactional PostgreSQL schema bootstrap and migration runner."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

import psycopg

from app.db.database import DATABASE_URL

API_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = API_ROOT / "app" / "db" / "schema.sql"
MIGRATIONS_DIR = API_ROOT / "migrations"
MIGRATION_LOCK_KEY = 1280262985
MIGRATION_NAME = re.compile(r"^\d{3}_[a-z0-9_]+\.sql$")


def migration_files() -> list[Path]:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    invalid = [path.name for path in files if not MIGRATION_NAME.fullmatch(path.name)]
    if invalid:
        raise RuntimeError(f"Invalid migration filenames: {', '.join(invalid)}")
    return files


def migration_checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def strip_transaction_wrappers(sql: str) -> str:
    """Remove only a migration's outer BEGIN/COMMIT for runner-owned atomicity."""
    lines = sql.splitlines(keepends=True)
    first = next((i for i, line in enumerate(lines) if line.strip() and not line.lstrip().startswith("--")), None)
    last = next((i for i in range(len(lines) - 1, -1, -1)
                 if lines[i].strip() and not lines[i].lstrip().startswith("--")), None)
    if first is not None and lines[first].strip().upper() == "BEGIN;":
        lines[first] = "\\n" if lines[first].endswith("\\n") else ""
    if last is not None and lines[last].strip().upper() == "COMMIT;":
        lines[last] = "\\n" if lines[last].endswith("\\n") else ""
    return "".join(lines)


def _ensure_tracking_table(connection: psycopg.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    connection.execute(
        "ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum TEXT"
    )


def _assert_bootstrap_schema(connection: psycopg.Connection) -> None:
    exists = connection.execute(
        "SELECT to_regclass('public.organizations') IS NOT NULL"
    ).fetchone()[0]
    if not exists:
        raise RuntimeError(
            "Core schema is missing. Run with --bootstrap for a new database, "
            "or apply app/db/schema.sql before migrating an existing database."
        )


def run_migrations(*, bootstrap: bool = False, check: bool = False) -> list[str]:
    """Apply pending migrations or verify the database matches migration files.

    Each migration and its checksum record are committed in one transaction.
    A PostgreSQL advisory lock prevents concurrent deploy jobs from racing.
    """
    applied: list[str] = []
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
        try:
            if bootstrap:
                if check:
                    raise ValueError("--bootstrap and --check cannot be combined")
                schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
                with connection.transaction():
                    connection.execute(schema_sql, prepare=False)

            _assert_bootstrap_schema(connection)
            _ensure_tracking_table(connection)

            for path in migration_files():
                sql = path.read_text(encoding="utf-8")
                checksum = migration_checksum(sql)
                version = path.stem
                record = connection.execute(
                    "SELECT checksum FROM schema_migrations WHERE version = %s",
                    (version,),
                ).fetchone()

                if record is not None:
                    recorded_checksum = record[0]
                    if recorded_checksum is None:
                        # Adopt legacy migration records created before checksums
                        # were tracked. Future edits are detected strictly.
                        connection.execute(
                            "UPDATE schema_migrations SET checksum = %s WHERE version = %s AND checksum IS NULL",
                            (checksum, version),
                        )
                    elif recorded_checksum != checksum:
                        raise RuntimeError(
                            f"Applied migration {version} has changed. "
                            "Create a new migration instead of editing an applied file."
                        )
                    continue

                if check:
                    raise RuntimeError(f"Migration {version} has not been applied")

                normalized_sql = strip_transaction_wrappers(sql)
                with connection.transaction():
                    connection.execute(normalized_sql, prepare=False)
                    connection.execute(
                        """
                        INSERT INTO schema_migrations (version, checksum)
                        VALUES (%s, %s)
                        ON CONFLICT (version) DO UPDATE
                        SET checksum = EXCLUDED.checksum
                        WHERE schema_migrations.checksum IS NULL
                        """,
                        (version, checksum),
                    )
                applied.append(version)
        finally:
            connection.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_KEY,))

    return applied


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap and migrate the logistics PostgreSQL database.")
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Apply the canonical idempotent schema before numbered migrations (new databases).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if any migration is pending or an applied migration checksum has changed.",
    )
    args = parser.parse_args()

    applied = run_migrations(bootstrap=args.bootstrap, check=args.check)
    if args.check:
        print("Database schema and migration checksums are up to date.")
    elif applied:
        print("Applied migrations: " + ", ".join(applied))
    else:
        print("Database schema is already up to date.")


if __name__ == "__main__":
    main()
