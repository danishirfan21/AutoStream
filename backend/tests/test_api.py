import asyncio

from httpx import ASGITransport, AsyncClient

from app.main import FIXTURES, app


def test_health() -> None:
    async def scenario() -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/health")).json() == {"status": "ok"}
    asyncio.run(scenario())


def test_fixture_directory_contains_known_csv() -> None:
    assert (FIXTURES / "dealer_feed_v1.csv").is_file()


def test_unknown_or_unsafe_fixture_is_rejected() -> None:
    async def scenario() -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.post("/api/v1/ingestion/csv?fixture=missing.csv")).status_code == 404
            assert (await client.post("/api/v1/ingestion/csv?fixture=../.env")).status_code == 404
            assert (await client.post("/api/v1/ingestion/json?fixture=missing.json")).status_code == 404
            assert (await client.post("/api/v1/ingestion/json?fixture=../.env")).status_code == 404
    asyncio.run(scenario())
