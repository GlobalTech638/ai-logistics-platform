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

COMMIT;
