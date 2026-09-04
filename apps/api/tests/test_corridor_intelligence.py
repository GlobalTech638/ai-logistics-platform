import pytest

from app.services.corridor_intelligence import assess_corridor_risk


def test_low_corridor_risk():
    result = assess_corridor_risk("Nairobi → Mombasa", 5)
    assert result.risk_level == "low"
    assert result.risk_score == 10.0


def test_high_corridor_risk():
    result = assess_corridor_risk("Nairobi → Kampala", 25, border_wait_hours=4)
    assert result.risk_level == "high"
    assert result.risk_score == 60.0
    assert "elevated delivery delays" in result.primary_factors


def test_negative_signal_rejected():
    with pytest.raises(ValueError):
        assess_corridor_risk("Nairobi → Kampala", -1)
