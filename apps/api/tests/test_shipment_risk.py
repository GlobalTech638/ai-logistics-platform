import pytest

from app.services.shipment_risk import assess_shipment_risk


def test_shipment_risk_combines_operational_signals():
    result = assess_shipment_risk(
        "SHP-001",
        corridor_risk_score=80,
        vehicle_health_score=40,
        delay_risk_pct=30,
        priority_weight=4,
    )

    assert result.risk_score >= 45
    assert result.risk_level in {"high", "critical"}
    assert "corridor risk" in result.factors
    assert result.recommended_action


def test_low_risk_shipment():
    result = assess_shipment_risk("SHP-002")
    assert result.risk_score == 0.0
    assert result.risk_level == "low"


def test_negative_signal_rejected():
    with pytest.raises(ValueError):
        assess_shipment_risk("SHP-003", corridor_risk_score=-1)
