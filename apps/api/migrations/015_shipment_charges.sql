BEGIN;
CREATE TABLE IF NOT EXISTS shipment_charges (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 shipment_id UUID NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
 charge_type TEXT NOT NULL CHECK (charge_type IN ('transport','handling','fuel_surcharge','waiting_time','other')),
 description TEXT NOT NULL CHECK (length(trim(description)) BETWEEN 1 AND 500),
 amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
 currency CHAR(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
 occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 created_by TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_shipment_charges_org_time ON shipment_charges(organization_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_shipment_charges_org_shipment ON shipment_charges(organization_id, shipment_id, occurred_at DESC);
CREATE TABLE IF NOT EXISTS shipment_charge_idempotency (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 shipment_id UUID NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
 idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
 request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
 response_body JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE (organization_id, shipment_id, idempotency_key)
);
CREATE OR REPLACE FUNCTION enforce_shipment_charge_integrity()
RETURNS trigger LANGUAGE plpgsql AS $guard$
DECLARE shipment_org UUID;
BEGIN
 IF TG_OP <> 'INSERT' THEN
  RAISE EXCEPTION 'Shipment charges are immutable ledger entries' USING ERRCODE = '23514';
 END IF;
 SELECT organization_id INTO shipment_org FROM shipments WHERE id = NEW.shipment_id;
 IF shipment_org IS NULL OR shipment_org <> NEW.organization_id THEN
  RAISE EXCEPTION 'Shipment charge must match its shipment tenant' USING ERRCODE = '23503';
 END IF;
 RETURN NEW;
END;
$guard$;
DROP TRIGGER IF EXISTS trg_shipment_charge_integrity ON shipment_charges;
CREATE TRIGGER trg_shipment_charge_integrity
BEFORE INSERT OR UPDATE OR DELETE ON shipment_charges
FOR EACH ROW EXECUTE FUNCTION enforce_shipment_charge_integrity();
COMMIT;
