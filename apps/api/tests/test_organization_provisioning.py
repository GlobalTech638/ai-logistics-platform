from contextlib import contextmanager

from fastapi.testclient import TestClient

from app import main
from app.db import database
from app.routes import organizations


client = TestClient(main.app)


def test_organization_creation_fails_closed_without_provisioning_token(monkeypatch):
    monkeypatch.delenv("ORGANIZATION_PROVISIONING_TOKEN", raising=False)

    def should_not_connect():
        raise AssertionError("unauthorized provisioning must not access the database")

    monkeypatch.setattr(organizations, "get_connection", should_not_connect)
    response = client.post(
        "/api/v1/organizations",
        json={"name": "Example Logistics", "country_code": "ke", "default_currency": "kes"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Organization provisioning is not authorized"


def test_organization_creation_rejects_wrong_provisioning_token(monkeypatch):
    monkeypatch.setenv("ORGANIZATION_PROVISIONING_TOKEN", "configured-secret")

    def should_not_connect():
        raise AssertionError("invalid provisioning credentials must not access the database")

    monkeypatch.setattr(organizations, "get_connection", should_not_connect)
    response = client.post(
        "/api/v1/organizations",
        headers={"X-Organization-Provisioning-Token": "wrong-secret"},
        json={"name": "Example Logistics", "country_code": "ke", "default_currency": "kes"},
    )

    assert response.status_code == 403


def test_organization_creation_accepts_configured_provisioning_token(monkeypatch):
    monkeypatch.setenv("ORGANIZATION_PROVISIONING_TOKEN", "configured-secret")

    class FakeCursor:
        description = [
            type("Column", (), {"name": "id"})(),
            type("Column", (), {"name": "name"})(),
            type("Column", (), {"name": "country_code"})(),
            type("Column", (), {"name": "default_currency"})(),
            type("Column", (), {"name": "created_at"})(),
        ]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params):
            self.query = query
            self.params = params

        def fetchone(self):
            return ("org-id", "Example Logistics", "KE", "KES", "2026-01-01T00:00:00Z")

    class FakeConnection:
        def __init__(self):
            self.fake_cursor = FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def cursor(self):
            return self.fake_cursor

    connection = FakeConnection()

    @contextmanager
    def fake_get_connection():
        yield connection

    monkeypatch.setattr(organizations, "get_connection", fake_get_connection)
    response = client.post(
        "/api/v1/organizations",
        headers={"X-Organization-Provisioning-Token": "configured-secret"},
        json={"name": "Example Logistics", "country_code": "ke", "default_currency": "kes"},
    )

    assert response.status_code == 200
    assert response.json()["country_code"] == "KE"
    assert response.json()["default_currency"] == "KES"
    assert connection.fake_cursor.params == ("Example Logistics", "KE", "KES")
