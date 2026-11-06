-- A vehicle may have only one unfinished trip at a time.
-- The partial unique index is the concurrency-safe authority; application
-- checks alone cannot prevent two dispatch transactions from racing.

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM trips
        WHERE completed_at IS NULL
        GROUP BY organization_id, vehicle_id
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Cannot enforce one active trip per vehicle: duplicate unfinished trips exist. Resolve them before applying migration 008.';
    END IF;
END;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_trips_one_active_per_vehicle
    ON trips (organization_id, vehicle_id)
    WHERE completed_at IS NULL;

COMMIT;
