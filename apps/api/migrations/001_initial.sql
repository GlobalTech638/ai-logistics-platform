-- Baseline migration for environments that apply migrations from an empty database.
-- The canonical bootstrap schema remains app/db/schema.sql.
-- This file establishes the migration directory and can be replaced by a generated
-- baseline when an external migration runner is introduced.

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO schema_migrations (version)
VALUES ('001_initial')
ON CONFLICT (version) DO NOTHING;

COMMIT;
