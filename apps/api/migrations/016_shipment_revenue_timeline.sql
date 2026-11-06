BEGIN;
ALTER TABLE shipment_events
    DROP CONSTRAINT IF EXISTS shipment_events_event_type_check;
ALTER TABLE shipment_events
    ADD CONSTRAINT shipment_events_event_type_check
    CHECK (event_type IN (
        'shipment_created',
        'vehicle_assigned',
        'assignment_released',
        'trip_started',
        'trip_completed',
        'fuel_recorded',
        'revenue_charge_recorded'
    ));
COMMIT;
