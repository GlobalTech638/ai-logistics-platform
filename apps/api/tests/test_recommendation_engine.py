import pytest

from app.services.recommendation_engine import build_recommendations


def test_reroute_recommendation_for_high_shipment_and_corridor_risk():
    recommendations = build_recommendations(
        "SHP-001",
        shipment_risk_score=80,
        shipment_risk_level="critical",
        corridor_risk_score=75,
    )

    assert recommendations[0].recommendation_type == "reroute_shipment"
    assert recommendations[0].priority == "critical"
    assert recommendations[0].actions


def test_vehicle_reassignment_is_recommended_when_vehicle_health_is_low():
    recommendations = build_recommendations(
        "SHP-002",
        shipment_risk_score=55,
        shipment_risk_level="high",
        vehicle_health_score=40,
    )

    assert any(item.recommendation_type == "reassign_vehicle" for item in recommendations)


def test_fuel_investigation_is_recommended_for_excess_cost():
    recommendations = build_recommendations(
        "SHP-003",
        shipment_risk_score=10,
        shipment_risk_level="low",
        estimated_excess_fuel_cost=1200,
        currency="kes",
    )

    recommendation = recommendations[0]
    assert recommendation.recommendation_type == "investigate_fuel_cost"
    assert "KES" in recommendation.rationale


def test_negative_input_rejected():
    with pytest.raises(ValueError):
        build_recommendations("SHP-004", shipment_risk_score=-1, shipment_risk_level="low")
