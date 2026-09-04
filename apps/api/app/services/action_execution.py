from dataclasses import dataclass


@dataclass(frozen=True)
class VehicleAssignmentDecision:
    allowed: bool
    reason: str


def validate_vehicle_reassignment(
    shipment_weight_tonnes: float,
    vehicle_capacity_tonnes: float,
    vehicle_active: bool,
) -> VehicleAssignmentDecision:
    if shipment_weight_tonnes <= 0:
        raise ValueError("shipment_weight_tonnes must be greater than zero")
    if vehicle_capacity_tonnes <= 0:
        raise ValueError("vehicle_capacity_tonnes must be greater than zero")

    if not vehicle_active:
        return VehicleAssignmentDecision(False, "Target vehicle is inactive")

    if vehicle_capacity_tonnes < shipment_weight_tonnes:
        return VehicleAssignmentDecision(False, "Target vehicle capacity is below shipment weight")

    return VehicleAssignmentDecision(True, "Vehicle is eligible for reassignment")
