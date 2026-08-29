from dataclasses import dataclass


@dataclass(frozen=True)
class LoadMatch:
    vehicle_id: str
    shipment_id: str
    utilization_percent: float
    deadhead_km: float
    score: float
    recommendation: str


def rank_load_matches(
    vehicles: list[dict],
    shipments: list[dict],
) -> list[LoadMatch]:
    matches: list[LoadMatch] = []

    for vehicle in vehicles:
        for shipment in shipments:
            if vehicle.get("available_from") != shipment.get("pickup_date"):
                continue
            if vehicle["destination"] != shipment["origin"]:
                continue
            if shipment["weight_tonnes"] > vehicle["capacity_tonnes"]:
                continue

            utilization = shipment["weight_tonnes"] / vehicle["capacity_tonnes"] * 100
            deadhead = max(float(vehicle.get("position_distance_km", 0)), 0)
            utilization_score = min(utilization, 100)
            score = max(0, utilization_score * 0.65 + max(0, 100 - deadhead / 5) * 0.35)

            matches.append(
                LoadMatch(
                    vehicle_id=vehicle["vehicle_id"],
                    shipment_id=shipment["shipment_id"],
                    utilization_percent=round(utilization, 1),
                    deadhead_km=deadhead,
                    score=round(score, 1),
                    recommendation="Strong match: assign this shipment to reduce empty capacity and deadhead distance.",
                )
            )

    return sorted(matches, key=lambda item: item.score, reverse=True)
