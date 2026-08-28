from dataclasses import dataclass

from app.schemas.trips import TripRecord, analyze_trip


@dataclass(frozen=True)
class CorridorSummary:
    corridor: str
    trip_count: int
    average_delay_percent: float
    delayed_trip_count: int
    risk: str
    recommendation: str


def summarize_corridors(trips: list[TripRecord]) -> list[CorridorSummary]:
    groups: dict[str, list[TripRecord]] = {}
    for trip in trips:
        key = f"{trip.origin} → {trip.destination}"
        groups.setdefault(key, []).append(trip)

    summaries = []
    for corridor, records in groups.items():
        results = [analyze_trip(record) for record in records]
        avg_delay = sum(item.delay_percent for item in results) / len(results)
        delayed = sum(item.delay_percent >= 8 for item in results)

        if avg_delay >= 30:
            risk = "critical"
            recommendation = "Replan departure windows and investigate recurring corridor constraints."
        elif avg_delay >= 15:
            risk = "high"
            recommendation = "Review route alternatives and historical congestion patterns."
        elif avg_delay >= 8:
            risk = "medium"
            recommendation = "Monitor corridor performance and identify repeat delay windows."
        else:
            risk = "low"
            recommendation = "Corridor is performing within the current operating tolerance."

        summaries.append(
            CorridorSummary(
                corridor=corridor,
                trip_count=len(records),
                average_delay_percent=round(avg_delay, 2),
                delayed_trip_count=delayed,
                risk=risk,
                recommendation=recommendation,
            )
        )

    return sorted(summaries, key=lambda item: item.average_delay_percent, reverse=True)
