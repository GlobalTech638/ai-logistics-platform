-- Add route-plan persistence to databases created before shipment_route_plans existed.
-- Safe to run repeatedly because the table and indexes are guarded.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS shipment_route_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    shipment_id UUID NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
    corridor TEXT NOT NULL,
    route_sequence INTEGER NOT NULL DEFAULT 1 CHECK (route_sequence > 0),
    status TEXT NOT NULL DEFAULT 'planned',
    reroute_reason TEXT,
    selected_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_shipment_route_plans_org_shipment
    ON shipment_route_plans(organization_id, shipment_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_shipment_route_plans_corridor
    ON shipment_route_plans(organization_id, corridor, status);

COMMIT;
