from __future__ import annotations

import html
import re
from urllib.parse import urljoin
from xml.etree import ElementTree

import httpx

from backend.config import get_settings
from backend.errors import WebSearchUnavailableError
from backend.models.schemas import WebSearchResult

_DUCKDUCKGO_URL = "https://html.duckduckgo.com/html/"
_SOGOU_URL = "https://www.sogou.com/web"
_BING_RSS_URL = "https://www.bing.com/search"
_DUCKDUCKGO_RESULT_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?(?:<a[^>]+class="result__snippet"[^>]*>(?P<snippet>.*?)</a>|<div[^>]+class="result__snippet"[^>]*>(?P<snippet_div>.*?)</div>)',
    re.S,
)
_SOGOU_RESULT_RE = re.compile(r'<h3[^>]*>\s*<a[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(value: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", value)).replace("\n", " ").strip()


def _limit(results: list[WebSearchResult], maximum: int) -> list[WebSearchResult]:
    return results[:maximum]


def _is_relevant(result: WebSearchResult, query: str) -> bool:
    terms = [term.lower() for term in re.split(r"\s+", query.strip()) if len(term) >= 2]
    if not terms:
        return True
    text = f"{result.title} {result.snippet}".lower()
    return any(term in text for term in terms)


def _filter_relevant(results: list[WebSearchResult], query: str, maximum: int) -> list[WebSearchResult]:
    return _limit([result for result in results if _is_relevant(result, query)], maximum)


async def _search_duckduckgo(client: httpx.AsyncClient, query: str, maximum: int) -> list[WebSearchResult]:
    response = await client.get(_DUCKDUCKGO_URL, params={"q": query}, headers={"User-Agent": "A3LearningAgent/1.0"})
    response.raise_for_status()
    results: list[WebSearchResult] = []
    for match in _DUCKDUCKGO_RESULT_RE.finditer(response.text):
        url = html.unescape(match.group("url")).strip()
        title = _clean(match.group("title"))
        snippet = _clean(match.group("snippet") or match.group("snippet_div") or "")
        if url.startswith("http") and title:
            results.append(WebSearchResult(title=title[:300], url=url[:2048], snippet=snippet[:1000]))
    return _filter_relevant(results, query, maximum)


async def _search_sogou(client: httpx.AsyncClient, query: str, maximum: int) -> list[WebSearchResult]:
    response = await client.get(_SOGOU_URL, params={"query": query}, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    results: list[WebSearchResult] = []
    for match in _SOGOU_RESULT_RE.finditer(response.text):
        title = _clean(match.group("title"))
        url = urljoin(str(response.url), html.unescape(match.group("url")).strip())
        if title and url.startswith("http"):
            results.append(WebSearchResult(title=title[:300], url=url[:2048], snippet=""))
    return _filter_relevant(results, query, maximum)


async def _search_bing(client: httpx.AsyncClient, query: str, maximum: int) -> list[WebSearchResult]:
    response = await client.get(
        _BING_RSS_URL,
        params={"q": query, "format": "rss"},
        headers={"User-Agent": "A3LearningAgent/1.0"},
    )
    response.raise_for_status()
    try:
        root = ElementTree.fromstring(response.text)
    except ElementTree.ParseError:
        return []
    results: list[WebSearchResult] = []
    for item in root.findall(".//item"):
        title = _clean(item.findtext("title", ""))
        url = (item.findtext("link", "") or "").strip()
        snippet = _clean(item.findtext("description", ""))
        if url.startswith("http") and title:
            results.append(WebSearchResult(title=title[:300], url=url[:2048], snippet=snippet[:1000]))
    return _filter_relevant(results, query, maximum)


async def search_web(query: str) -> list[WebSearchResult]:
    settings = get_settings()
    if not settings.web_search_enabled:
        return []
    providers = [provider.strip().lower() for provider in settings.web_search_providers.split(",") if provider.strip()]
    provider_functions = {"sogou": _search_sogou, "duckduckgo": _search_duckduckgo, "bing": _search_bing}
    usable_providers = [provider for provider in providers if provider in provider_functions]
    if not usable_providers:
        return []

    successful_response = False
    async with httpx.AsyncClient(timeout=settings.web_search_timeout_seconds, follow_redirects=True) as client:
        for provider in usable_providers:
            try:
                results = await provider_functions[provider](client, query, settings.web_search_max_results)
                successful_response = True
            except httpx.HTTPError:
                continue
            if results:
                return results
    if not successful_response:
        raise WebSearchUnavailableError()
    return []


async def search_web_optional(query: str) -> list[WebSearchResult]:
    try:
        return await search_web(query)
    except WebSearchUnavailableError:
        return []