-- Append-only operational history for recommendation actions.
-- Apply after the existing route-plan migrations. Safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS recommendation_action_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    action_id UUID NOT NULL REFERENCES recommendation_actions(id) ON DELETE CASCADE,
    from_status TEXT,
    to_status TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    event_type TEXT NOT NULL DEFAULT 'status_transition',
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recommendation_action_events_action_time
    ON recommendation_action_events(action_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_action_events_org_time
    ON recommendation_action_events(organization_id, created_at DESC);

COMMIT;
