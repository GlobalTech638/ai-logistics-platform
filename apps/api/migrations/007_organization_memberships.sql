-- Trusted organization membership and role lifecycle for production identity.
-- Apply after the canonical schema and migrations 002-006.

BEGIN;

CREATE TABLE IF NOT EXISTS organization_memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_subject TEXT NOT NULL CHECK (length(user_subject) BETWEEN 1 AND 255),
    role TEXT NOT NULL CHECK (
        role IN ('admin', 'operations_manager', 'fleet_manager', 'analyst', 'viewer')
    ),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'revoked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, user_subject)
);

CREATE INDEX IF NOT EXISTS idx_organization_memberships_subject_status
    ON organization_memberships(user_subject, status);

CREATE INDEX IF NOT EXISTS idx_organization_memberships_org_status
    ON organization_memberships(organization_id, status);

COMMIT;
