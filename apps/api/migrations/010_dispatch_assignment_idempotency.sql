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

CREATE OR REPLACE FUNCTION enforce_dispatch_assignment_idempotency_tenant()
RETURNS trigger
LANGUAGE plpgsql
AS $dispatch_tenant$
DECLARE
    shipment_organization_id UUID;
BEGIN
    SELECT organization_id INTO shipment_organization_id
    FROM shipments WHERE id = NEW.shipment_id;

    IF shipment_organization_id IS NULL
       OR shipment_organization_id <> NEW.organization_id THEN
        RAISE EXCEPTION 'Dispatch idempotency record must belong to the shipment organization'
            USING ERRCODE = '23503';
    END IF;

    RETURN NEW;
END;
$dispatch_tenant$;

DROP TRIGGER IF EXISTS trg_dispatch_assignment_idempotency_tenant
    ON dispatch_assignment_idempotency;
CREATE TRIGGER trg_dispatch_assignment_idempotency_tenant
BEFORE INSERT OR UPDATE OF organization_id, shipment_id
ON dispatch_assignment_idempotency
FOR EACH ROW EXECUTE FUNCTION enforce_dispatch_assignment_idempotency_tenant();

COMMIT;
