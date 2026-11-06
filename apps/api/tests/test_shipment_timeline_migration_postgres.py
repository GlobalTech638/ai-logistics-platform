import os
from uuid import uuid4

import pytest
from psycopg.errors import CheckViolation
from psycopg.types.json import Jsonb

from app.db.database import get_connection


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL is required for PostgreSQL migration tests",
)
def test_shipment_timeline_events_are_immutable_and_cascade_with_parent():
    suffix = uuid4().hex[:10]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (name, country_code, default_currency)
                VALUES (%s, 'KE', 'KES') RETURNING id
                """,
                (f"Timeline integrity {suffix}",),
            )
            organization_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO shipments (
                    organization_id, shipment_reference, origin, destination,
                    weight_tonnes, status
                ) VALUES (%s, %s, 'Nairobi', 'Nakuru', 2, 'pending')
                RETURNING id
                """,
                (organization_id, f"TIMELINE-{suffix}"),
            )
            shipment_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO shipment_events (
                    organization_id, shipment_id, event_type, actor_id, details
                ) VALUES (%s, %s, 'shipment_created', %s, %s)
                RETURNING id
                """,
                (organization_id, shipment_id, f"operator-{suffix}", Jsonb({"test": True})),
            )
            event_id = cur.fetchone()[0]

    with pytest.raises(CheckViolation):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE shipment_events SET actor_id = 'tampered' WHERE id = %s",
                    (event_id,),
                )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM shipments WHERE organization_id = %s AND id = %s",
                (organization_id, shipment_id),
            )
            cur.execute("SELECT count(*) FROM shipment_events WHERE id = %s", (event_id,))
            assert cur.fetchone()[0] == 0
