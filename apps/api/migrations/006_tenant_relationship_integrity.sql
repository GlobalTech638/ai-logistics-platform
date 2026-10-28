-- Prevent cross-tenant relationships even when data is written outside the API.
-- Run after the canonical schema and migrations 002-005. Safe to re-run.

BEGIN;

CREATE OR REPLACE FUNCTION enforce_same_organization_relationships()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    related_organization_id UUID;
BEGIN
    IF TG_TABLE_NAME = 'trips' THEN
        SELECT organization_id INTO related_organization_id
        FROM vehicles WHERE id = NEW.vehicle_id;
        IF related_organization_id IS NULL OR related_organization_id <> NEW.organization_id THEN
            RAISE EXCEPTION 'Trip vehicle must belong to the same organization'
                USING ERRCODE = '23503';
        END IF;
        IF NEW.shipment_id IS NOT NULL THEN
            SELECT organization_id INTO related_organization_id
            FROM shipments WHERE id = NEW.shipment_id;
            IF related_organization_id IS NULL OR related_organization_id <> NEW.organization_id THEN
                RAISE EXCEPTION 'Trip shipment must belong to the same organization'
                    USING ERRCODE = '23503';
            END IF;
        END IF;
    ELSIF TG_TABLE_NAME = 'fuel_transactions' THEN
        SELECT organization_id INTO related_organization_id
        FROM vehicles WHERE id = NEW.vehicle_id;
        IF related_organization_id IS NULL OR related_organization_id <> NEW.organization_id THEN
            RAISE EXCEPTION 'Fuel transaction vehicle must belong to the same organization'
                USING ERRCODE = '23503';
        END IF;
        IF NEW.trip_id IS NOT NULL THEN
            SELECT organization_id INTO related_organization_id
            FROM trips WHERE id = NEW.trip_id;
            IF related_organization_id IS NULL OR related_organization_id <> NEW.organization_id THEN
                RAISE EXCEPTION 'Fuel transaction trip must belong to the same organization'
                    USING ERRCODE = '23503';
            END IF;
        END IF;
    ELSIF TG_TABLE_NAME = 'maintenance_events' THEN
        SELECT organization_id INTO related_organization_id
        FROM vehicles WHERE id = NEW.vehicle_id;
        IF related_organization_id IS NULL OR related_organization_id <> NEW.organization_id THEN
            RAISE EXCEPTION 'Maintenance vehicle must belong to the same organization'
                USING ERRCODE = '23503';
        END IF;
    ELSIF TG_TABLE_NAME = 'alerts' THEN
        IF NEW.vehicle_id IS NOT NULL THEN
            SELECT organization_id INTO related_organization_id
            FROM vehicles WHERE id = NEW.vehicle_id;
            IF related_organization_id IS NULL OR related_organization_id <> NEW.organization_id THEN
                RAISE EXCEPTION 'Alert vehicle must belong to the same organization'
                    USING ERRCODE = '23503';
            END IF;
        END IF;
        IF NEW.shipment_id IS NOT NULL THEN
            SELECT organization_id INTO related_organization_id
            FROM shipments WHERE id = NEW.shipment_id;
            IF related_organization_id IS NULL OR related_organization_id <> NEW.organization_id THEN
                RAISE EXCEPTION 'Alert shipment must belong to the same organization'
                    USING ERRCODE = '23503';
            END IF;
        END IF;
    ELSIF TG_TABLE_NAME = 'recommendation_actions' THEN
        IF NEW.shipment_id IS NOT NULL THEN
            SELECT organization_id INTO related_organization_id
            FROM shipments WHERE id = NEW.shipment_id;
            IF related_organization_id IS NULL OR related_organization_id <> NEW.organization_id THEN
                RAISE EXCEPTION 'Recommendation shipment must belong to the same organization'
                    USING ERRCODE = '23503';
            END IF;
        END IF;
    ELSIF TG_TABLE_NAME = 'recommendation_action_events' THEN
        SELECT organization_id INTO related_organization_id
        FROM recommendation_actions WHERE id = NEW.action_id;
        IF related_organization_id IS NULL OR related_organization_id <> NEW.organization_id THEN
            RAISE EXCEPTION 'Recommendation event action must belong to the same organization'
                USING ERRCODE = '23503';
        END IF;
    ELSIF TG_TABLE_NAME = 'recommendation_action_idempotency' THEN
        SELECT organization_id INTO related_organization_id
        FROM recommendation_actions WHERE id = NEW.action_id;
        IF related_organization_id IS NULL OR related_organization_id <> NEW.organization_id THEN
            RAISE EXCEPTION 'Idempotency action must belong to the same organization'
                USING ERRCODE = '23503';
        END IF;
    ELSIF TG_TABLE_NAME = 'shipment_route_plans' THEN
        SELECT organization_id INTO related_organization_id
        FROM shipments WHERE id = NEW.shipment_id;
        IF related_organization_id IS NULL OR related_organization_id <> NEW.organization_id THEN
            RAISE EXCEPTION 'Route plan shipment must belong to the same organization'
                USING ERRCODE = '23503';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_trips_same_organization ON trips;
CREATE TRIGGER trg_trips_same_organization
BEFORE INSERT OR UPDATE OF organization_id, vehicle_id, shipment_id ON trips
FOR EACH ROW EXECUTE FUNCTION enforce_same_organization_relationships();

DROP TRIGGER IF EXISTS trg_fuel_transactions_same_organization ON fuel_transactions;
CREATE TRIGGER trg_fuel_transactions_same_organization
BEFORE INSERT OR UPDATE OF organization_id, vehicle_id, trip_id ON fuel_transactions
FOR EACH ROW EXECUTE FUNCTION enforce_same_organization_relationships();

DROP TRIGGER IF EXISTS trg_maintenance_events_same_organization ON maintenance_events;
CREATE TRIGGER trg_maintenance_events_same_organization
BEFORE INSERT OR UPDATE OF organization_id, vehicle_id ON maintenance_events
FOR EACH ROW EXECUTE FUNCTION enforce_same_organization_relationships();

DROP TRIGGER IF EXISTS trg_alerts_same_organization ON alerts;
CREATE TRIGGER trg_alerts_same_organization
BEFORE INSERT OR UPDATE OF organization_id, vehicle_id, shipment_id ON alerts
FOR EACH ROW EXECUTE FUNCTION enforce_same_organization_relationships();

DROP TRIGGER IF EXISTS trg_recommendation_actions_same_organization ON recommendation_actions;
CREATE TRIGGER trg_recommendation_actions_same_organization
BEFORE INSERT OR UPDATE OF organization_id, shipment_id ON recommendation_actions
FOR EACH ROW EXECUTE FUNCTION enforce_same_organization_relationships();

DROP TRIGGER IF EXISTS trg_recommendation_action_events_same_organization ON recommendation_action_events;
CREATE TRIGGER trg_recommendation_action_events_same_organization
BEFORE INSERT OR UPDATE OF organization_id, action_id ON recommendation_action_events
FOR EACH ROW EXECUTE FUNCTION enforce_same_organization_relationships();

DROP TRIGGER IF EXISTS trg_recommendation_action_idempotency_same_organization ON recommendation_action_idempotency;
CREATE TRIGGER trg_recommendation_action_idempotency_same_organization
BEFORE INSERT OR UPDATE OF organization_id, action_id ON recommendation_action_idempotency
FOR EACH ROW EXECUTE FUNCTION enforce_same_organization_relationships();

DROP TRIGGER IF EXISTS trg_shipment_route_plans_same_organization ON shipment_route_plans;
CREATE TRIGGER trg_shipment_route_plans_same_organization
BEFORE INSERT OR UPDATE OF organization_id, shipment_id ON shipment_route_plans
FOR EACH ROW EXECUTE FUNCTION enforce_same_organization_relationships();


-- Tenant ownership is immutable after row creation. Without this guard, a
-- parent row could be moved to another tenant and invalidate relationships
-- that were checked only when the child was inserted or updated.
CREATE OR REPLACE FUNCTION prevent_tenant_ownership_change()
RETURNS trigger
LANGUAGE plpgsql
AS $
BEGIN
    IF NEW.organization_id IS DISTINCT FROM OLD.organization_id THEN
        RAISE EXCEPTION 'Tenant ownership cannot be changed after creation'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$;

DROP TRIGGER IF EXISTS trg_vehicles_tenant_immutable ON vehicles;
CREATE TRIGGER trg_vehicles_tenant_immutable
BEFORE UPDATE OF organization_id ON vehicles
FOR EACH ROW EXECUTE FUNCTION prevent_tenant_ownership_change();

DROP TRIGGER IF EXISTS trg_shipments_tenant_immutable ON shipments;
CREATE TRIGGER trg_shipments_tenant_immutable
BEFORE UPDATE OF organization_id ON shipments
FOR EACH ROW EXECUTE FUNCTION prevent_tenant_ownership_change();

DROP TRIGGER IF EXISTS trg_trips_tenant_immutable ON trips;
CREATE TRIGGER trg_trips_tenant_immutable
BEFORE UPDATE OF organization_id ON trips
FOR EACH ROW EXECUTE FUNCTION prevent_tenant_ownership_change();

DROP TRIGGER IF EXISTS trg_fuel_transactions_tenant_immutable ON fuel_transactions;
CREATE TRIGGER trg_fuel_transactions_tenant_immutable
BEFORE UPDATE OF organization_id ON fuel_transactions
FOR EACH ROW EXECUTE FUNCTION prevent_tenant_ownership_change();

DROP TRIGGER IF EXISTS trg_maintenance_events_tenant_immutable ON maintenance_events;
CREATE TRIGGER trg_maintenance_events_tenant_immutable
BEFORE UPDATE OF organization_id ON maintenance_events
FOR EACH ROW EXECUTE FUNCTION prevent_tenant_ownership_change();

DROP TRIGGER IF EXISTS trg_alerts_tenant_immutable ON alerts;
CREATE TRIGGER trg_alerts_tenant_immutable
BEFORE UPDATE OF organization_id ON alerts
FOR EACH ROW EXECUTE FUNCTION prevent_tenant_ownership_change();

DROP TRIGGER IF EXISTS trg_recommendation_actions_tenant_immutable ON recommendation_actions;
CREATE TRIGGER trg_recommendation_actions_tenant_immutable
BEFORE UPDATE OF organization_id ON recommendation_actions
FOR EACH ROW EXECUTE FUNCTION prevent_tenant_ownership_change();

DROP TRIGGER IF EXISTS trg_recommendation_action_events_tenant_immutable ON recommendation_action_events;
CREATE TRIGGER trg_recommendation_action_events_tenant_immutable
BEFORE UPDATE OF organization_id ON recommendation_action_events
FOR EACH ROW EXECUTE FUNCTION prevent_tenant_ownership_change();

DROP TRIGGER IF EXISTS trg_recommendation_action_idempotency_tenant_immutable ON recommendation_action_idempotency;
CREATE TRIGGER trg_recommendation_action_idempotency_tenant_immutable
BEFORE UPDATE OF organization_id ON recommendation_action_idempotency
FOR EACH ROW EXECUTE FUNCTION prevent_tenant_ownership_change();

DROP TRIGGER IF EXISTS trg_shipment_route_plans_tenant_immutable ON shipment_route_plans;
CREATE TRIGGER trg_shipment_route_plans_tenant_immutable
BEFORE UPDATE OF organization_id ON shipment_route_plans
FOR EACH ROW EXECUTE FUNCTION prevent_tenant_ownership_change();

COMMIT;
