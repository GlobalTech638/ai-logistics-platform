-- Idempotent operator dispatch commands. Keys are scoped to tenant and shipment.
BEGIN;

CREATE TABLE IF NOT EXISTS dispatch_assignment_idempotency (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    shipment_id UUID NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    response_body JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, shipment_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_dispatch_assignment_idempotency_created
    ON dispatch_assignment_idempotency (organization_id, created_at DESC);

COMMIT;
