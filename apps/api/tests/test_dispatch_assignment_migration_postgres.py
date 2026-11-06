import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import errors
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL is required for PostgreSQL migration integration tests",
)
def test_dispatch_assignment_migration_is_rerunnable_and_enforces_history():
    migration = (API_ROOT / "migrations/009_shipment_vehicle_assignments.sql").read_text()
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        # The CI job has already applied this migration; applying it again
        # verifies safe re-runs on an initialized installation.
        conn.execute(migration, prepare=False)

        suffix = uuid4().hex[:10]
        org_id = conn.execute(
            """
            INSERT INTO organizations (name, country_code, default_currency)
            VALUES (%s, 'KE', 'KES') RETURNING id
            """,
            (f"Assignment migration {suffix}",),
        ).fetchone()[0]
        other_org_id = conn.execute(
            """
            INSERT INTO organizations (name, country_code, default_currency)
            VALUES (%s, 'KE', 'KES') RETURNING id
            """,
            (f"Other assignment migration {suffix}",),
        ).fetchone()[0]

        vehicle_id = conn.execute(
            """
            INSERT INTO vehicles (organization_id, registration_number, make, model,
                                  expected_litres_per_100km, capacity_tonnes)
            VALUES (%s, %s, 'Test', 'Truck', 20, 10) RETURNING id
            """,
            (org_id, f"ASSIGN-{suffix}"),
        ).fetchone()[0]
        other_vehicle_id = conn.execute(
            """
            INSERT INTO vehicles (organization_id, registration_number, make, model,
                                  expected_litres_per_100km, capacity_tonnes)
            VALUES (%s, %s, 'Test', 'Truck', 20, 10) RETURNING id
            """,
            (other_org_id, f"OTHER-{suffix}"),
        ).fetchone()[0]
        shipment_id = conn.execute(
            """
            INSERT INTO shipments (organization_id, shipment_reference, origin,
                                   destination, weight_tonnes)
            VALUES (%s, %s, 'Nairobi', 'Mombasa', 4) RETURNING id
            """,
            (org_id, f"LOAD-{suffix}"),
        ).fetchone()[0]
        second_shipment_id = conn.execute(
            """
            INSERT INTO shipments (organization_id, shipment_reference, origin,
                                   destination, weight_tonnes)
            VALUES (%s, %s, 'Nairobi', 'Kisumu', 3) RETURNING id
            """,
            (org_id, f"LOAD2-{suffix}"),
        ).fetchone()[0]

        assignment_id = conn.execute(
            """
            INSERT INTO shipment_vehicle_assignments
                (organization_id, shipment_id, vehicle_id, assigned_by)
            VALUES (%s, %s, %s, 'operator-1') RETURNING id
            """,
            (org_id, shipment_id, vehicle_id),
        ).fetchone()[0]

        with pytest.raises(errors.UniqueViolation):
            conn.execute(
                """
                INSERT INTO shipment_vehicle_assignments
                    (organization_id, shipment_id, vehicle_id, assigned_by)
                VALUES (%s, %s, %s, 'operator-2')
                """,
                (org_id, second_shipment_id, vehicle_id),
            )
        with pytest.raises(errors.ForeignKeyViolation):
            conn.execute(
                """
                INSERT INTO shipment_vehicle_assignments
                    (organization_id, shipment_id, vehicle_id, assigned_by)
                VALUES (%s, %s, %s, 'operator-2')
                """,
                (org_id, shipment_id, other_vehicle_id),
            )

        conn.execute(
            "UPDATE shipment_vehicle_assignments SET released_at = now() WHERE id = %s",
            (assignment_id,),
        )
        replacement_id = conn.execute(
            """
            INSERT INTO shipment_vehicle_assignments
                (organization_id, shipment_id, vehicle_id, assigned_by)
            VALUES (%s, %s, %s, 'operator-2') RETURNING id
            """,
            (org_id, second_shipment_id, vehicle_id),
        ).fetchone()[0]
        assert replacement_id is not None

        with pytest.raises(errors.CheckViolation):
            conn.execute(
                "UPDATE shipment_vehicle_assignments SET vehicle_id = %s WHERE id = %s",
                (other_vehicle_id, replacement_id),
            )
