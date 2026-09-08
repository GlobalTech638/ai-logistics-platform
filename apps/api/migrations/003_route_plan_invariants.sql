-- Enforce the route-plan lifecycle at the database boundary.
-- Run after 002_route_plans.sql on existing PostgreSQL databases.
-- The unique index intentionally fails if legacy data contains multiple active
-- plans for one shipment; clean that data before applying this migration.

BEGIN;

ALTER TABLE shipment_route_plans
    ADD CONSTRAINT shipment_route_plans_status_check
    CHECK (status IN ('planned', 'active', 'superseded'));

CREATE UNIQUE INDEX IF NOT EXISTS uq_shipment_route_plans_one_active
    ON shipment_route_plans(shipment_id)
    WHERE status = 'active';

COMMIT;
