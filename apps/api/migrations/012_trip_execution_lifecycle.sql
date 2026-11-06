-- Model trip execution separately from dispatch reservation.
BEGIN;

ALTER TABLE trips
    ALTER COLUMN actual_duration_minutes DROP NOT NULL,
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS started_by TEXT,
    ADD COLUMN IF NOT EXISTS start_odometer_km NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS end_odometer_km NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS actual_distance_km NUMERIC(12,2),
    ADD COLUMN IF NOT EXISTS completed_by TEXT;

UPDATE trips
SET started_at = COALESCE(
    started_at,
    CASE
        WHEN completed_at IS NOT NULL
        THEN completed_at - (actual_duration_minutes * INTERVAL '1 minute')
        ELSE now()
    END
)
WHERE started_at IS NULL;

ALTER TABLE trips
    ALTER COLUMN started_at SET DEFAULT now(),
    ALTER COLUMN started_at SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_trip_actual_distance_positive'
          AND conrelid = 'trips'::regclass
    ) THEN
        ALTER TABLE trips
            ADD CONSTRAINT ck_trip_actual_distance_positive
            CHECK (actual_distance_km IS NULL OR actual_distance_km > 0);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_trip_odometer_order'
          AND conrelid = 'trips'::regclass
    ) THEN
        ALTER TABLE trips
            ADD CONSTRAINT ck_trip_odometer_order
            CHECK (
                start_odometer_km IS NULL
                OR end_odometer_km IS NULL
                OR end_odometer_km > start_odometer_km
            );
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS trip_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    trip_id UUID NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    shipment_id UUID NOT NULL REFERENCES shipments(id),
    vehicle_id UUID NOT NULL REFERENCES vehicles(id),
    event_type TEXT NOT NULL CHECK (event_type IN ('started', 'completed')),
    actor_id TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trip_events_org_time
    ON trip_events (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trip_events_trip_time
    ON trip_events (trip_id, created_at DESC);

CREATE OR REPLACE FUNCTION enforce_trip_event_integrity()
RETURNS trigger
LANGUAGE plpgsql
AS $trip_event$
DECLARE
    trip_org UUID;
    trip_shipment UUID;
    trip_vehicle UUID;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Trip events are append-only' USING ERRCODE = '23514';
    END IF;

    SELECT organization_id, shipment_id, vehicle_id
      INTO trip_org, trip_shipment, trip_vehicle
    FROM trips WHERE id = NEW.trip_id;

    IF trip_org IS NULL
       OR trip_org <> NEW.organization_id
       OR trip_shipment <> NEW.shipment_id
       OR trip_vehicle <> NEW.vehicle_id THEN
        RAISE EXCEPTION 'Trip event must match its trip tenant and entities'
            USING ERRCODE = '23503';
    END IF;
    RETURN NEW;
END;
$trip_event$;

DROP TRIGGER IF EXISTS trg_trip_event_integrity ON trip_events;
CREATE TRIGGER trg_trip_event_integrity
BEFORE INSERT OR UPDATE OR DELETE ON trip_events
FOR EACH ROW EXECUTE FUNCTION enforce_trip_event_integrity();

CREATE TABLE IF NOT EXISTS trip_command_idempotency (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    shipment_id UUID NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    response_body JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, shipment_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_trip_command_idempotency_org_time
    ON trip_command_idempotency (organization_id, created_at DESC);

COMMIT;
