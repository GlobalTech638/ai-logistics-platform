-- Add an auditable release lifecycle to dispatch assignments.
BEGIN;

ALTER TABLE shipment_vehicle_assignments
    ADD COLUMN IF NOT EXISTS released_by TEXT,
    ADD COLUMN IF NOT EXISTS release_reason TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_dispatch_assignment_release_actor'
          AND conrelid = 'shipment_vehicle_assignments'::regclass
    ) THEN
        ALTER TABLE shipment_vehicle_assignments
            ADD CONSTRAINT ck_dispatch_assignment_release_actor
            CHECK (
                (released_at IS NULL AND released_by IS NULL)
                OR (released_at IS NOT NULL AND released_by IS NOT NULL)
            );
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_dispatch_assignment_release_reason'
          AND conrelid = 'shipment_vehicle_assignments'::regclass
    ) THEN
        ALTER TABLE shipment_vehicle_assignments
            ADD CONSTRAINT ck_dispatch_assignment_release_reason
            CHECK (release_reason IS NULL OR length(release_reason) <= 500);
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS dispatch_assignment_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    assignment_id UUID NOT NULL REFERENCES shipment_vehicle_assignments(id) ON DELETE CASCADE,
    shipment_id UUID NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
    vehicle_id UUID NOT NULL REFERENCES vehicles(id),
    event_type TEXT NOT NULL CHECK (event_type IN ('assigned', 'released')),
    actor_id TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dispatch_assignment_events_org_time
    ON dispatch_assignment_events (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_dispatch_assignment_events_assignment_time
    ON dispatch_assignment_events (assignment_id, created_at DESC);

CREATE OR REPLACE FUNCTION enforce_dispatch_assignment_release_immutability()
RETURNS trigger
LANGUAGE plpgsql
AS $dispatch_release$
BEGIN
    IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
       OR NEW.shipment_id IS DISTINCT FROM OLD.shipment_id
       OR NEW.vehicle_id IS DISTINCT FROM OLD.vehicle_id
       OR NEW.assigned_by IS DISTINCT FROM OLD.assigned_by
       OR NEW.assigned_at IS DISTINCT FROM OLD.assigned_at
       OR (OLD.released_at IS NOT NULL AND (
            NEW.released_at IS DISTINCT FROM OLD.released_at
            OR NEW.released_by IS DISTINCT FROM OLD.released_by
            OR NEW.release_reason IS DISTINCT FROM OLD.release_reason
       ))
       OR (OLD.released_at IS NULL AND NEW.released_at IS NULL AND (
            NEW.released_by IS DISTINCT FROM OLD.released_by
            OR NEW.release_reason IS DISTINCT FROM OLD.release_reason
       ))
       OR (OLD.released_at IS NOT NULL AND NEW.released_at IS NULL) THEN
        RAISE EXCEPTION 'Dispatch assignment history is immutable except for one release'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$dispatch_release$;

DROP TRIGGER IF EXISTS trg_dispatch_assignment_integrity ON shipment_vehicle_assignments;
CREATE TRIGGER trg_dispatch_assignment_integrity
BEFORE UPDATE ON shipment_vehicle_assignments
FOR EACH ROW EXECUTE FUNCTION enforce_dispatch_assignment_release_immutability();

CREATE OR REPLACE FUNCTION enforce_dispatch_assignment_event_integrity()
RETURNS trigger
LANGUAGE plpgsql
AS $dispatch_event$
DECLARE
    assignment_org UUID;
    assignment_shipment UUID;
    assignment_vehicle UUID;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Dispatch assignment events are append-only'
            USING ERRCODE = '23514';
    END IF;

    SELECT organization_id, shipment_id, vehicle_id
      INTO assignment_org, assignment_shipment, assignment_vehicle
    FROM shipment_vehicle_assignments
    WHERE id = NEW.assignment_id;

    IF assignment_org IS NULL
       OR assignment_org <> NEW.organization_id
       OR assignment_shipment <> NEW.shipment_id
       OR assignment_vehicle <> NEW.vehicle_id THEN
        RAISE EXCEPTION 'Dispatch event must match its assignment tenant and entities'
            USING ERRCODE = '23503';
    END IF;

    RETURN NEW;
END;
$dispatch_event$;

DROP TRIGGER IF EXISTS trg_dispatch_assignment_event_integrity ON dispatch_assignment_events;
CREATE TRIGGER trg_dispatch_assignment_event_integrity
BEFORE INSERT OR UPDATE OR DELETE ON dispatch_assignment_events
FOR EACH ROW EXECUTE FUNCTION enforce_dispatch_assignment_event_integrity();

COMMIT;
