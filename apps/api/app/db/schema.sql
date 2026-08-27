CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    country_code CHAR(2) NOT NULL,
    default_currency CHAR(3) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS vehicles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    registration_number TEXT NOT NULL,
    make TEXT NOT NULL,
    model TEXT NOT NULL,
    fuel_type TEXT NOT NULL DEFAULT 'diesel',
    expected_litres_per_100km NUMERIC(8,2) NOT NULL CHECK (expected_litres_per_100km > 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (organization_id, registration_number)
);

CREATE TABLE IF NOT EXISTS fuel_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    vehicle_id UUID NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    transaction_time TIMESTAMPTZ NOT NULL,
    litres NUMERIC(12,3) NOT NULL CHECK (litres > 0),
    price_per_litre NUMERIC(14,4) NOT NULL CHECK (price_per_litre >= 0),
    odometer_km NUMERIC(14,2) NOT NULL CHECK (odometer_km >= 0),
    currency CHAR(3) NOT NULL,
    country_code CHAR(2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vehicles_org ON vehicles(organization_id);
CREATE INDEX IF NOT EXISTS idx_fuel_vehicle_time ON fuel_transactions(vehicle_id, transaction_time);
CREATE INDEX IF NOT EXISTS idx_fuel_org_time ON fuel_transactions(organization_id, transaction_time);
