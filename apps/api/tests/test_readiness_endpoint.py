from contextlib import contextmanager

from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)


class FakeCursor:
    def __init__(self):
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query):
        self.executed.append(query)

    def fetchone(self):
        return (1,)


class FakeConnection:
    def __init__(self):
        self.fake_cursor = FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self.fake_cursor


def test_ready_returns_200_when_database_query_succeeds(monkeypatch):
    connection = FakeConnection()

    @contextmanager
    def fake_get_connection():
        yield connection

    monkeypatch.setattr(main, "get_connection", fake_get_connection)
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}
    assert connection.fake_cursor.executed == ["SELECT 1"]


def test_ready_returns_503_when_database_is_unavailable(monkeypatch):
    @contextmanager
    def failing_connection():
        raise RuntimeError("database unavailable")
        yield  # pragma: no cover

    monkeypatch.setattr(main, "get_connection", failing_connection)
    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "dependency": "database"}


def test_liveness_health_does_not_require_database(monkeypatch):
    def should_not_connect():
        raise AssertionError("liveness endpoint must not check database")

    monkeypatch.setattr(main, "get_connection", should_not_connect)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
