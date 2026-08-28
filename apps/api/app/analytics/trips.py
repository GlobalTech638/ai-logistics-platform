from app.schemas.trips import TripIntelligence, TripRecord, analyze_trip


def rank_trip_risk(trips: list[TripRecord]) -> list[TripIntelligence]:
    results = [analyze_trip(trip) for trip in trips]
    return sorted(results, key=lambda item: item.delay_percent, reverse=True)


SAMPLE_TRIPS = [
    TripRecord(
        vehicle_id="KE-KDA-431A",
        origin="Nairobi",
        destination="Mombasa",
        distance_km=485,
        planned_duration_minutes=420,
        actual_duration_minutes=575,
        load_tonnes=12,
        completed_at="2026-08-27T16:00:00Z",
        country_code="KE",
    ),
    TripRecord(
        vehicle_id="UG-UAX-204K",
        origin="Kampala",
        destination="Mombasa",
        distance_km=1170,
        planned_duration_minutes=1100,
        actual_duration_minutes=1230,
        load_tonnes=18,
        completed_at="2026-08-27T18:00:00Z",
        country_code="UG",
    ),
    TripRecord(
        vehicle_id="TZ-T-482B",
        origin="Dar es Salaam",
        destination="Arusha",
        distance_km=640,
        planned_duration_minutes=600,
        actual_duration_minutes=620,
        load_tonnes=10,
        completed_at="2026-08-27T15:00:00Z",
        country_code="TZ",
    ),
]
