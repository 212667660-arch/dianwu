import asyncio

from fastapi.testclient import TestClient

from backend.errors import WebSearchUnavailableError
from backend.main import app
from backend.models.schemas import WebSearchResult
from backend.routers import web


def test_web_search_route_returns_sources(monkeypatch) -> None:
    async def search(query: str):
        assert query == "一次函数"
        return [WebSearchResult(title="教学资料", url="https://example.test/math", snippet="一次函数")]

    monkeypatch.setattr(web, "search_web", search)
    with TestClient(app) as client:
        response = client.post("/api/web/search", json={"query": "一次函数"})
    assert response.status_code == 200
    assert response.json()["results"][0]["url"] == "https://example.test/math"


def test_web_search_route_returns_structured_network_error(monkeypatch) -> None:
    async def unavailable(query: str):
        raise WebSearchUnavailableError()

    monkeypatch.setattr(web, "search_web", unavailable)
    with TestClient(app) as client:
        response = client.post("/api/web/search", json={"query": "一次函数"})
    assert response.status_code == 503
    assert response.json()["code"] == "WEB_SEARCH_UNAVAILABLE"