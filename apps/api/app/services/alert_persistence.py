from uuid import UUID

from app.db.database import get_connection
from app.services.alert_engine import AlertDecision


def persist_alerts(
    organization_id: UUID,
    vehicle_id: UUID,
    decisions: list[AlertDecision],
) -> int:
    if not decisions:
        return 0

    query = """
        INSERT INTO alerts (
            organization_id, vehicle_id, alert_type, severity,
            score, message, recommended_action
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    with get_connection() as connection:
        with connection.cursor() as cursor:
            for decision in decisions:
                cursor.execute(
                    query,
                    (
                        organization_id,
                        vehicle_id,
                        decision.alert_type,
                        decision.severity,
                        decision.score,
                        decision.message,
                        decision.recommended_action,
                    ),
                )

    return len(decisions)
