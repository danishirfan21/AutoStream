from fastapi.testclient import TestClient

from app.main import FIXTURES, app


def test_health() -> None:
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_fixture_directory_contains_known_csv() -> None:
    assert (FIXTURES / "dealer_feed_v1.csv").is_file()


def test_unknown_or_unsafe_fixture_is_rejected() -> None:
    with TestClient(app) as client:
        assert client.post("/api/v1/ingestion/csv?fixture=missing.csv").status_code == 404
        assert client.post("/api/v1/ingestion/csv?fixture=../.env").status_code == 404
        assert client.post("/api/v1/ingestion/json?fixture=missing.json").status_code == 404
        assert client.post("/api/v1/ingestion/json?fixture=../.env").status_code == 404
