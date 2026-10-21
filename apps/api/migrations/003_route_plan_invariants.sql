-- Enforce route-plan lifecycle and invariants at the database boundary.
-- Run after 002_route_plans.sql on existing PostgreSQL databases.
-- Safe to re-run. Existing duplicate active plans must be cleaned before
-- creating the partial unique index.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'shipment_route_plans_status_check'
          AND conrelid = 'shipment_route_plans'::regclass
    ) THEN
        ALTER TABLE shipment_route_plans
            ADD CONSTRAINT shipment_route_plans_status_check
            CHECK (status IN ('planned', 'active', 'superseded'));
    END IF;
END;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_shipment_route_plans_one_active
    ON shipment_route_plans(shipment_id)
    WHERE status = 'active';

CREATE OR REPLACE FUNCTION enforce_shipment_route_plan_lifecycle()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status = 'superseded' THEN
        RAISE EXCEPTION 'Superseded route plans are immutable'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.status IS DISTINCT FROM OLD.status
       AND NOT (
           (OLD.status = 'planned' AND NEW.status = 'active')
           OR (OLD.status = 'active' AND NEW.status = 'superseded')
       ) THEN
        RAISE EXCEPTION 'Invalid route plan transition: % -> %', OLD.status, NEW.status
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_shipment_route_plan_lifecycle
    ON shipment_route_plans;

CREATE TRIGGER trg_shipment_route_plan_lifecycle
BEFORE UPDATE ON shipment_route_plans
FOR EACH ROW
EXECUTE FUNCTION enforce_shipment_route_plan_lifecycle();

COMMIT;
