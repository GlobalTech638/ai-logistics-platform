import logging
import re

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_response_returns_request_id():
    response = client.get("/health", headers={"X-Request-ID": "dispatch-req-42"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "dispatch-req-42"


def test_invalid_request_id_is_replaced():
    response = client.get("/health", headers={"X-Request-ID": "bad request id with spaces"})

    assert response.status_code == 200
    assert re.fullmatch(r"[0-9a-f-]{36}", response.headers["X-Request-ID"])


def test_request_completion_log_contains_correlation_and_duration(caplog):
    with caplog.at_level(logging.INFO, logger="logistics_api.http"):
        response = client.get("/health", headers={"X-Request-ID": "audit-test-7"})

    assert response.status_code == 200
    records = [
        record for record in caplog.records
        if record.name == "logistics_api.http" and record.message == "http_request_completed"
    ]
    assert records
    record = records[-1]
    assert record.request_id == "audit-test-7"
    assert record.method == "GET"
    assert record.path == "/health"
    assert record.status_code == 200
    assert record.duration_ms >= 0



def test_metrics_endpoint_exposes_low_cardinality_request_counters():
    response = client.get("/health")

    assert response.status_code == 200
    metrics_response = client.get("/metrics")

    assert metrics_response.status_code == 200
    body = metrics_response.text
    assert "# TYPE logistics_http_requests_total counter" in body
    assert 'logistics_http_requests_total{method="GET",route="/health",status_class="2xx"}' in body
    assert "logistics_http_request_duration_seconds_sum" in body
    assert 'route="/health"' in body
