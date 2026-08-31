from uuid import UUID

from app.db.database import get_connection


def list_vehicles(organization_id: UUID) -> list[dict]:
    query = """
        SELECT id, vehicle_id, registration_number, vehicle_type,
               capacity_tonnes, odometer_km, status
        FROM vehicles
        WHERE organization_id = %s
        ORDER BY vehicle_id
    """
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (organization_id,))
            columns = [item.name for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def list_open_alerts(organization_id: UUID) -> list[dict]:
    query = """
        SELECT id, vehicle_id, shipment_id, alert_type, severity,
               score, message, recommended_action, created_at
        FROM alerts
        WHERE organization_id = %s AND status = 'open'
        ORDER BY created_at DESC
    """
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (organization_id,))
            columns = [item.name for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
