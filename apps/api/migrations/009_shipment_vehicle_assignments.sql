-- Keep dispatch assignment separate from trip execution telemetry.
-- An assignment reserves a vehicle for a shipment; a trip is created when
-- the journey actually starts and carries distance/duration measurements.

BEGIN;

CREATE TABLE IF NOT EXISTS shipment_vehicle_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    shipment_id UUID NOT NULL REFERENCES shipments(id),
    vehicle_id UUID NOT NULL REFERENCES vehicles(id),
    assigned_by TEXT NOT NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    released_at TIMESTAMPTZ,
    CHECK (released_at IS NULL OR released_at >= assigned_at)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_dispatch_assignment_active_shipment
    ON shipment_vehicle_assignments (organization_id, shipment_id)
    WHERE released_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_dispatch_assignment_active_vehicle
    ON shipment_vehicle_assignments (organization_id, vehicle_id)
    WHERE released_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_dispatch_assignments_org_assigned
    ON shipment_vehicle_assignments (organization_id, assigned_at DESC);

CREATE OR REPLACE FUNCTION enforce_dispatch_assignment_integrity()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    related_organization_id UUID;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
           OR NEW.shipment_id IS DISTINCT FROM OLD.shipment_id
           OR NEW.vehicle_id IS DISTINCT FROM OLD.vehicle_id
           OR NEW.assigned_by IS DISTINCT FROM OLD.assigned_by
           OR NEW.assigned_at IS DISTINCT FROM OLD.assigned_at
           OR (OLD.released_at IS NOT NULL AND NEW.released_at IS DISTINCT FROM OLD.released_at)
           OR (NEW.released_at IS NULL AND OLD.released_at IS NOT NULL) THEN
            RAISE EXCEPTION 'Dispatch assignment history is immutable except for release'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    SELECT organization_id INTO related_organization_id
    FROM shipments WHERE id = NEW.shipment_id;
    IF related_organization_id IS NULL OR related_organization_id <> NEW.organization_id THEN
        RAISE EXCEPTION 'Dispatch assignment shipment must belong to the same organization'
            USING ERRCODE = '23503';
    END IF;

    SELECT organization_id INTO related_organization_id
    FROM vehicles WHERE id = NEW.vehicle_id;
    IF related_organization_id IS NULL OR related_organization_id <> NEW.organization_id THEN
        RAISE EXCEPTION 'Dispatch assignment vehicle must belong to the same organization'
            USING ERRCODE = '23503';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_dispatch_assignment_integrity ON shipment_vehicle_assignments;
CREATE TRIGGER trg_dispatch_assignment_integrity
BEFORE INSERT OR UPDATE ON shipment_vehicle_assignments
FOR EACH ROW EXECUTE FUNCTION enforce_dispatch_assignment_integrity();

COMMIT;
