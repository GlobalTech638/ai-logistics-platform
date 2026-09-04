CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    country_code CHAR(2) NOT NULL,
    default_currency CHAR(3) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vehicles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    registration_number TEXT NOT NULL,
    make TEXT NOT NULL,
    model TEXT NOT NULL,
    fuel_type TEXT NOT NULL DEFAULT 'diesel',
    expected_litres_per_100km NUMERIC(8,2) NOT NULL CHECK (expected_litres_per_100km > 0),
    capacity_tonnes NUMERIC(10,2) CHECK (capacity_tonnes > 0),
    odometer_km NUMERIC(14,2) NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, registration_number)
);

CREATE TABLE IF NOT EXISTS shipments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    shipment_reference TEXT NOT NULL,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    weight_tonnes NUMERIC(10,2) NOT NULL CHECK (weight_tonnes > 0),
    pickup_at TIMESTAMPTZ,
    delivery_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, shipment_reference)
);

CREATE TABLE IF NOT EXISTS trips (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    vehicle_id UUID NOT NULL REFERENCES vehicles(id),
    shipment_id UUID REFERENCES shipments(id),
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    distance_km NUMERIC(12,2) NOT NULL CHECK (distance_km > 0),
    planned_duration_minutes INTEGER NOT NULL CHECK (planned_duration_minutes > 0),
    actual_duration_minutes INTEGER NOT NULL CHECK (actual_duration_minutes > 0),
    load_tonnes NUMERIC(10,2) NOT NULL DEFAULT 0,
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS fuel_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    vehicle_id UUID NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    trip_id UUID REFERENCES trips(id),
    transaction_time TIMESTAMPTZ NOT NULL,
    litres NUMERIC(12,3) NOT NULL CHECK (litres > 0),
    price_per_litre NUMERIC(14,4) NOT NULL CHECK (price_per_litre >= 0),
    odometer_km NUMERIC(14,2) NOT NULL CHECK (odometer_km >= 0),
    currency CHAR(3) NOT NULL,
    country_code CHAR(2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS maintenance_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    vehicle_id UUID NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    service_type TEXT NOT NULL,
    odometer_km NUMERIC(14,2) NOT NULL,
    cost NUMERIC(14,2),
    currency CHAR(3),
    completed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    vehicle_id UUID REFERENCES vehicles(id),
    shipment_id UUID REFERENCES shipments(id),
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    score NUMERIC(6,2),
    message TEXT NOT NULL,
    recommended_action TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recommendation_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    shipment_id UUID REFERENCES shipments(id) ON DELETE SET NULL,
    recommendation_type TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'medium',
    recommendation_score NUMERIC(6,2),
    title TEXT,
    rationale TEXT,
    expected_impact TEXT,
    status TEXT NOT NULL DEFAULT 'proposed',
    notes TEXT,
    acted_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_vehicles_org ON vehicles(organization_id);
CREATE INDEX IF NOT EXISTS idx_shipments_org_status ON shipments(organization_id, status);
CREATE INDEX IF NOT EXISTS idx_trips_org_completed ON trips(organization_id, completed_at);
CREATE INDEX IF NOT EXISTS idx_fuel_vehicle_time ON fuel_transactions(vehicle_id, transaction_time);
CREATE INDEX IF NOT EXISTS idx_alerts_org_status ON alerts(organization_id, status);
CREATE INDEX IF NOT EXISTS idx_recommendation_actions_org_created ON recommendation_actions(organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_recommendation_actions_org_status ON recommendation_actions(organization_id, status);
CREATE INDEX IF NOT EXISTS idx_recommendation_actions_shipment ON recommendation_actions(shipment_id, created_at DESC);
