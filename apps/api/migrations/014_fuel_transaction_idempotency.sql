BEGIN;

ALTER TABLE shipment_events
    DROP CONSTRAINT IF EXISTS shipment_events_event_type_check;

ALTER TABLE shipment_events
    ADD CONSTRAINT shipment_events_event_type_check
    CHECK (
        event_type IN (
            'shipment_created',
            'vehicle_assigned',
            'assignment_released',
            'trip_started',
            'trip_completed',
            'fuel_recorded'
        )
    );

CREATE TABLE IF NOT EXISTS fuel_transaction_idempotency (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    response_body JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_fuel_transaction_idempotency_org_time
    ON fuel_transaction_idempotency (organization_id, created_at DESC);

COMMIT;
