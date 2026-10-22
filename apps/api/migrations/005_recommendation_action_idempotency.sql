-- Idempotent recommendation-action status requests.
-- A replay with the same key and request returns the original response.
-- Reusing a key with a different request is rejected.

BEGIN;

CREATE TABLE IF NOT EXISTS recommendation_action_idempotency (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    action_id UUID NOT NULL REFERENCES recommendation_actions(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    response_body JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, action_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_recommendation_action_idempotency_created
    ON recommendation_action_idempotency(organization_id, created_at DESC);

COMMIT;
