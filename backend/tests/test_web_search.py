import asyncio

import httpx

from backend.config import Settings
from backend.errors import WebSearchUnavailableError
from backend.services import web_search


class Response:
    def __init__(self, text: str) -> None:
        self.text = text
        self.url = "https://www.sogou.com/web"

    def raise_for_status(self) -> None:
        return None


class Client:
    def __init__(self, responses) -> None:
        self.responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, params=None, headers=None):
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_search_web_parses_limited_duckduckgo_results(monkeypatch) -> None:
    html = '<a class="result__a" href="https://example.test/a">数学资料</a><a class="result__snippet">一次函数知识点</a><a class="result__a" href="https://example.test/b">英语资料</a><div class="result__snippet">时态练习</div>'
    monkeypatch.setattr(web_search, "get_settings", lambda: Settings(web_search_providers="duckduckgo", web_search_max_results=1))
    monkeypatch.setattr(web_search.httpx, "AsyncClient", lambda **kwargs: Client([Response(html)]))
    results = asyncio.run(web_search.search_web("一次函数"))
    assert len(results) == 1
    assert results[0].title == "数学资料"
    assert results[0].url == "https://example.test/a"


def test_search_web_falls_back_to_bing_rss(monkeypatch) -> None:
    rss = """<rss><channel><item><title>一次函数资料</title><link>https://example.test/math</link><description>教学参考</description></item></channel></rss>"""
    monkeypatch.setattr(web_search, "get_settings", lambda: Settings(web_search_providers="duckduckgo,bing"))
    monkeypatch.setattr(web_search.httpx, "AsyncClient", lambda **kwargs: Client([httpx.ConnectError("offline"), Response(rss)]))
    results = asyncio.run(web_search.search_web("一次函数"))
    assert len(results) == 1
    assert results[0].title == "一次函数资料"
    assert results[0].snippet == "教学参考"


def test_optional_search_degrades_when_all_providers_are_unavailable(monkeypatch) -> None:
    async def unavailable(query):
        raise WebSearchUnavailableError()

    monkeypatch.setattr(web_search, "search_web", unavailable)
    assert asyncio.run(web_search.search_web_optional("一次函数")) == []

def test_search_web_parses_sogou_results_and_filters_irrelevant_entries(monkeypatch) -> None:
    html = '''<h3><a href="/link?url=lesson">一次函数教学设计</a></h3><h3><a href="/link?url=other">汉字一的解释</a></h3>'''
    monkeypatch.setattr(web_search, "get_settings", lambda: Settings(web_search_providers="sogou", web_search_max_results=5))
    monkeypatch.setattr(web_search.httpx, "AsyncClient", lambda **kwargs: Client([Response(html)]))
    results = asyncio.run(web_search.search_web("一次函数 数学"))
    assert len(results) == 1
    assert results[0].title == "一次函数教学设计"
    assert results[0].url == "https://www.sogou.com/link?url=lesson"