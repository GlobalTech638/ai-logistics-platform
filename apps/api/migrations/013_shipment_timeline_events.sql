BEGIN;

CREATE TABLE IF NOT EXISTS shipment_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    shipment_id UUID NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'shipment_created',
            'vehicle_assigned',
            'assignment_released',
            'trip_started',
            'trip_completed'
        )
    ),
    actor_id TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_shipment_events_org_shipment_time
    ON shipment_events (organization_id, shipment_id, occurred_at, id);
CREATE INDEX IF NOT EXISTS idx_shipment_events_org_time
    ON shipment_events (organization_id, occurred_at DESC);

CREATE OR REPLACE FUNCTION enforce_shipment_event_integrity()
RETURNS trigger
LANGUAGE plpgsql
AS $shipment_event$
DECLARE
    shipment_org UUID;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Shipment events are append-only'
            USING ERRCODE = '23514';
    END IF;

    SELECT organization_id INTO shipment_org
    FROM shipments WHERE id = NEW.shipment_id;

    IF shipment_org IS NULL OR shipment_org <> NEW.organization_id THEN
        RAISE EXCEPTION 'Shipment event must match its shipment tenant'
            USING ERRCODE = '23503';
    END IF;

    RETURN NEW;
END;
$shipment_event$;

DROP TRIGGER IF EXISTS trg_shipment_event_integrity ON shipment_events;
CREATE TRIGGER trg_shipment_event_integrity
BEFORE INSERT OR UPDATE OR DELETE ON shipment_events
FOR EACH ROW EXECUTE FUNCTION enforce_shipment_event_integrity();


-- Backfill milestones for records that existed before the timeline API shipped.
INSERT INTO shipment_events (
    organization_id, shipment_id, event_type, actor_id, details, occurred_at
)
SELECT s.organization_id, s.id, 'shipment_created', 'system:migration',
       jsonb_build_object(
           'shipment_reference', s.shipment_reference,
           'origin', s.origin,
           'destination', s.destination,
           'weight_tonnes', s.weight_tonnes,
           'legacy_backfill', true
       ),
       s.created_at
FROM shipments s
WHERE NOT EXISTS (
    SELECT 1 FROM shipment_events e
    WHERE e.organization_id = s.organization_id
      AND e.shipment_id = s.id
      AND e.event_type = 'shipment_created'
);

INSERT INTO shipment_events (
    organization_id, shipment_id, event_type, actor_id, details, occurred_at
)
SELECT a.organization_id, a.shipment_id, 'vehicle_assigned', a.assigned_by,
       jsonb_build_object(
           'assignment_id', a.id,
           'vehicle_id', a.vehicle_id,
           'legacy_backfill', true
       ),
       a.assigned_at
FROM shipment_vehicle_assignments a
WHERE NOT EXISTS (
    SELECT 1 FROM shipment_events e
    WHERE e.organization_id = a.organization_id
      AND e.shipment_id = a.shipment_id
      AND e.event_type = 'vehicle_assigned'
      AND e.occurred_at = a.assigned_at
);

INSERT INTO shipment_events (
    organization_id, shipment_id, event_type, actor_id, details, occurred_at
)
SELECT a.organization_id, a.shipment_id, 'assignment_released', a.released_by,
       jsonb_build_object(
           'assignment_id', a.id,
           'vehicle_id', a.vehicle_id,
           'reason', a.release_reason,
           'legacy_backfill', true
       ),
       a.released_at
FROM shipment_vehicle_assignments a
WHERE a.released_at IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM shipment_events e
      WHERE e.organization_id = a.organization_id
        AND e.shipment_id = a.shipment_id
        AND e.event_type = 'assignment_released'
        AND e.occurred_at = a.released_at
  );

INSERT INTO shipment_events (
    organization_id, shipment_id, event_type, actor_id, details, occurred_at
)
SELECT t.organization_id, t.shipment_id, 'trip_started',
       COALESCE(t.started_by, 'system:migration'),
       jsonb_build_object(
           'trip_id', t.id,
           'vehicle_id', t.vehicle_id,
           'start_odometer_km', t.start_odometer_km,
           'legacy_backfill', true
       ),
       t.started_at
FROM trips t
WHERE t.shipment_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM shipment_events e
      WHERE e.organization_id = t.organization_id
        AND e.shipment_id = t.shipment_id
        AND e.event_type = 'trip_started'
        AND e.occurred_at = t.started_at
  );

INSERT INTO shipment_events (
    organization_id, shipment_id, event_type, actor_id, details, occurred_at
)
SELECT t.organization_id, t.shipment_id, 'trip_completed',
       COALESCE(t.completed_by, 'system:migration'),
       jsonb_build_object(
           'trip_id', t.id,
           'vehicle_id', t.vehicle_id,
           'actual_distance_km', t.actual_distance_km,
           'actual_duration_minutes', t.actual_duration_minutes,
           'legacy_backfill', true
       ),
       t.completed_at
FROM trips t
WHERE t.shipment_id IS NOT NULL
  AND t.completed_at IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM shipment_events e
      WHERE e.organization_id = t.organization_id
        AND e.shipment_id = t.shipment_id
        AND e.event_type = 'trip_completed'
        AND e.occurred_at = t.completed_at
  );

COMMIT;
