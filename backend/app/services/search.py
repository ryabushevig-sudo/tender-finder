"""Supplier search via DuckDuckGo HTML and lightweight page scraping."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from selectolax.parser import HTMLParser

from app.core.config import settings
from app.core.logging import logger

DDG_HTML_ENDPOINT = "https://html.duckduckgo.com/html/"

# Marketplaces / aggregators we'd usually skip when looking for direct suppliers.
DEFAULT_EXCLUDED_DOMAINS = {
    "wildberries.ru",
    "ozon.ru",
    "market.yandex.ru",
    "aliexpress.ru",
    "avito.ru",
    "youla.ru",
    "youtube.com",
    "wikipedia.org",
    "ru.wikipedia.org",
    "zakupki.gov.ru",
    "rts-tender.ru",
}

# Restrict supplier search to the Russian Federation only. We accept any domain
# whose host ends with one of these suffixes. .рф is the IDN top-level domain
# for Russia; it appears either as "рф" (decoded) or "xn--p1ai" (punycode)
# depending on how the URL was emitted, so we check both.
ALLOWED_TLD_SUFFIXES: tuple[str, ...] = (
    ".ru",
    ".рф",
    ".xn--p1ai",  # punycode form of .рф
    ".su",
)

PRICE_PATTERNS = [
    # Matches: "12 345,67 руб", "1 250 ₽", but caps the digit group at 7 digits
    # so that long article numbers are not slurped in.
    re.compile(
        r"(?<![\d.])(\d{1,3}(?:[\s\u00a0]\d{3}){0,2}(?:[.,]\d{1,2})?|\d{1,7})"
        r"\s*(?:руб(?:\.|лей)?|₽|RUB)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:цена|стоимость)\s*[:\-]?\s*"
        r"(\d{1,3}(?:[\s\u00a0]\d{3}){0,2}(?:[.,]\d{1,2})?|\d{1,7})",
        re.IGNORECASE,
    ),
]

PHONE_PATTERN = re.compile(
    r"(?:\+7|8)[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}"
)
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    domain: str = ""
    price: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    raw_extract: dict[str, str] = field(default_factory=dict)


def _normalize_ddg_url(href: str) -> str:
    """DDG HTML wraps real URLs in /l/?uddg=<encoded>."""
    if not href:
        return ""
    parsed = urlparse(href)
    if parsed.path.endswith("/l/") or parsed.path == "/l/":
        qs = parse_qs(parsed.query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    if href.startswith("//"):
        return "https:" + href
    return href


def _domain(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def _is_russian_domain(host: str) -> bool:
    """True iff the host (or any sub-host) ends in a Russian TLD."""
    if not host:
        return False
    host = host.lower().rstrip(".")
    return any(host.endswith(suffix) for suffix in ALLOWED_TLD_SUFFIXES)


async def search_suppliers(
    query: str,
    *,
    max_results: int | None = None,
    excluded_domains: set[str] | None = None,
) -> list[SearchResult]:
    """Search DuckDuckGo HTML for supplier pages relevant to the query."""
    excluded = (excluded_domains or set()) | DEFAULT_EXCLUDED_DOMAINS
    limit = max_results or settings.max_search_results

    # Restrict to Russian suppliers via the `kl=ru-ru` region hint below and
    # the TLD whitelist below. We intentionally do NOT inject `site:` operators
    # into the query — DDG often returns a wait/anti-bot page when the query
    # has multiple operators, breaking the search entirely.
    augmented = f"{query} купить"
    logger.info("Search query: {}", augmented)

    import asyncio as _asyncio

    async with httpx.AsyncClient(
        timeout=settings.request_timeout_seconds,
        headers={"User-Agent": settings.search_user_agent},
        follow_redirects=True,
    ) as client:
        html = ""
        # DDG sometimes returns a 202 "anti-bot wait" page when it's nervous
        # about a request. Retry a couple of times with a short backoff.
        for attempt in range(3):
            response = await client.post(
                DDG_HTML_ENDPOINT,
                data={"q": augmented, "kl": "ru-ru"},
            )
            if response.status_code == 200 and "result__a" in response.text:
                html = response.text
                break
            if response.status_code in (202, 429):
                logger.info(
                    "DDG returned {} on attempt {}; backing off",
                    response.status_code,
                    attempt + 1,
                )
                await _asyncio.sleep(1.5 * (attempt + 1))
                continue
            response.raise_for_status()
            html = response.text
            break

    parser = HTMLParser(html)
    results: list[SearchResult] = []
    for result_node in parser.css("div.result"):
        if len(results) >= limit:
            break
        a = result_node.css_first("a.result__a")
        if a is None:
            continue
        href = a.attributes.get("href", "") or ""
        url = _normalize_ddg_url(href)
        if not url.startswith("http"):
            continue
        domain = _domain(url)
        if not domain or any(domain.endswith(d) for d in excluded):
            continue
        if not _is_russian_domain(domain):
            continue
        title = (a.text() or "").strip()
        snippet_node = result_node.css_first(".result__snippet")
        snippet = (snippet_node.text() if snippet_node else "").strip()
        results.append(
            SearchResult(title=title, url=url, snippet=snippet, domain=domain)
        )

    # Enrich top results with prices/contacts (best-effort, parallel)
    import asyncio

    async def enrich(r: SearchResult) -> None:
        try:
            await _enrich_result(r)
        except Exception as exc:  # pragma: no cover - network best-effort
            logger.debug("Enrichment failed for {}: {}", r.url, exc)

    await asyncio.gather(*(enrich(r) for r in results))
    return results


async def _enrich_result(result: SearchResult) -> None:
    """Fetch the page and try to extract price + phone + email."""
    async with httpx.AsyncClient(
        timeout=settings.request_timeout_seconds,
        headers={"User-Agent": settings.search_user_agent},
        follow_redirects=True,
    ) as client:
        try:
            response = await client.get(result.url)
        except httpx.RequestError:
            return
        if response.status_code != 200:
            return
        ctype = response.headers.get("content-type", "")
        if "html" not in ctype.lower():
            return
        html = response.text

    parser = HTMLParser(html)
    text = parser.text(separator=" ")
    text = re.sub(r"\s+", " ", text)[:20000]

    for pattern in PRICE_PATTERNS:
        match = pattern.search(text)
        if match:
            value = match.group(1).strip()
            result.price = f"{value} ₽"
            break

    phone_match = PHONE_PATTERN.search(text)
    if phone_match:
        result.contact_phone = phone_match.group(0)

    email_match = EMAIL_PATTERN.search(text)
    if email_match:
        result.contact_email = email_match.group(0)

    if result.price or result.contact_phone or result.contact_email:
        result.raw_extract["text_sample"] = text[:500]
