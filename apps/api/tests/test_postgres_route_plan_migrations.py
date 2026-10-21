import os
from pathlib import Path

import psycopg
import pytest
from psycopg import errors


API_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL is required for PostgreSQL migration integration tests",
)
def test_route_plan_migrations_are_rerunnable_and_enforce_invariants():
    database_url = os.environ["DATABASE_URL"]

    with psycopg.connect(database_url, autocommit=True) as conn:
        # The CI database is disposable. Build the canonical schema, then
        # simulate an older installation that predates route-plan persistence.
        conn.execute((API_ROOT / "app/db/schema.sql").read_text(), prepare=False)
        conn.execute("DROP TABLE IF EXISTS shipment_route_plans CASCADE")

        conn.execute((API_ROOT / "migrations/002_route_plans.sql").read_text(), prepare=False)
        migration_003 = (API_ROOT / "migrations/003_route_plan_invariants.sql").read_text()
        conn.execute(migration_003, prepare=False)
        conn.execute(migration_003, prepare=False)

        organization_id = conn.execute(
            """
            INSERT INTO organizations (name, country_code, default_currency)
            VALUES ('Migration test', 'KE', 'KES')
            RETURNING id
            """
        ).fetchone()[0]
        shipment_id = conn.execute(
            """
            INSERT INTO shipments (
                organization_id, shipment_reference, origin, destination, weight_tonnes
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (organization_id, "MIGRATION-TEST-001", "Nairobi", "Mombasa", 2),
        ).fetchone()[0]

        conn.execute(
            """
            INSERT INTO shipment_route_plans
                (organization_id, shipment_id, corridor, status)
            VALUES (%s, %s, %s, 'active')
            """,
            (organization_id, shipment_id, "Nairobi-Mombasa"),
        )

        with pytest.raises(errors.UniqueViolation):
            conn.execute(
                """
                INSERT INTO shipment_route_plans
                    (organization_id, shipment_id, corridor, status)
                VALUES (%s, %s, %s, 'active')
                """,
                (organization_id, shipment_id, "Alternative corridor"),
            )

        with pytest.raises(errors.CheckViolation):
            conn.execute(
                """
                INSERT INTO shipment_route_plans
                    (organization_id, shipment_id, corridor, status)
                VALUES (%s, %s, %s, 'invalid')
                """,
                (organization_id, shipment_id, "Invalid status"),
            )
