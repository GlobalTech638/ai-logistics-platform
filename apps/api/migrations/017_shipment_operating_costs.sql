BEGIN;

CREATE TABLE IF NOT EXISTS shipment_operating_costs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    shipment_id UUID NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
    trip_id UUID,
    cost_type TEXT NOT NULL CHECK (cost_type IN (
        'driver_allowance', 'toll', 'parking', 'border_fee',
        'maintenance', 'insurance', 'loading', 'unloading', 'other'
    )),
    description TEXT NOT NULL CHECK (length(trim(description)) BETWEEN 1 AND 500),
    amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    currency CHAR(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_shipment_operating_costs_org_time
    ON shipment_operating_costs(organization_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_shipment_operating_costs_org_shipment
    ON shipment_operating_costs(organization_id, shipment_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS shipment_operating_cost_idempotency (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    shipment_id UUID NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    response_body JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, shipment_id, idempotency_key)
);

CREATE OR REPLACE FUNCTION enforce_shipment_operating_cost_integrity()
RETURNS trigger LANGUAGE plpgsql AS $guard$
DECLARE
    shipment_org UUID;
    trip_org UUID;
    trip_shipment UUID;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'Shipment operating costs and idempotency records are immutable'
            USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'DELETE' THEN
        PERFORM 1 FROM shipments WHERE id = OLD.shipment_id;
        IF FOUND THEN
            RAISE EXCEPTION 'Shipment operating costs and idempotency records are immutable'
                USING ERRCODE = '23514';
        END IF;
        RETURN OLD;
    END IF;

    SELECT organization_id INTO shipment_org
    FROM shipments WHERE id = NEW.shipment_id;
    IF shipment_org IS NULL OR shipment_org <> NEW.organization_id THEN
        RAISE EXCEPTION 'Shipment operating cost must match its shipment tenant'
            USING ERRCODE = '23503';
    END IF;

    IF TG_TABLE_NAME = 'shipment_operating_costs' AND NEW.trip_id IS NOT NULL THEN
        SELECT organization_id, shipment_id INTO trip_org, trip_shipment
        FROM trips WHERE id = NEW.trip_id;
        IF trip_org IS NULL OR trip_org <> NEW.organization_id
           OR trip_shipment IS DISTINCT FROM NEW.shipment_id THEN
            RAISE EXCEPTION 'Operating cost trip must belong to the same shipment and tenant'
                USING ERRCODE = '23503';
        END IF;
    END IF;
    RETURN NEW;
END;
$guard$;

DROP TRIGGER IF EXISTS trg_shipment_operating_cost_integrity ON shipment_operating_costs;
CREATE TRIGGER trg_shipment_operating_cost_integrity
BEFORE INSERT OR UPDATE OR DELETE ON shipment_operating_costs
FOR EACH ROW EXECUTE FUNCTION enforce_shipment_operating_cost_integrity();

DROP TRIGGER IF EXISTS trg_shipment_operating_cost_idempotency_integrity ON shipment_operating_cost_idempotency;
CREATE TRIGGER trg_shipment_operating_cost_idempotency_integrity
BEFORE INSERT OR UPDATE OR DELETE ON shipment_operating_cost_idempotency
FOR EACH ROW EXECUTE FUNCTION enforce_shipment_operating_cost_integrity();

DROP TRIGGER IF EXISTS trg_shipment_operating_costs_tenant_immutable ON shipment_operating_costs;
CREATE TRIGGER trg_shipment_operating_costs_tenant_immutable
BEFORE UPDATE OF organization_id ON shipment_operating_costs
FOR EACH ROW EXECUTE FUNCTION prevent_tenant_ownership_change();

DROP TRIGGER IF EXISTS trg_shipment_operating_cost_idempotency_tenant_immutable ON shipment_operating_cost_idempotency;
CREATE TRIGGER trg_shipment_operating_cost_idempotency_tenant_immutable
BEFORE UPDATE OF organization_id ON shipment_operating_cost_idempotency
FOR EACH ROW EXECUTE FUNCTION prevent_tenant_ownership_change();

ALTER TABLE shipment_events
    DROP CONSTRAINT IF EXISTS shipment_events_event_type_check;
ALTER TABLE shipment_events
    ADD CONSTRAINT shipment_events_event_type_check
    CHECK (event_type IN (
        'shipment_created',
        'vehicle_assigned',
        'assignment_released',
        'trip_started',
        'trip_completed',
        'fuel_recorded',
        'revenue_charge_recorded',
        'operating_cost_recorded'
    ));

COMMIT;
