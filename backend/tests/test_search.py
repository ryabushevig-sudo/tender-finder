"""Tests for the supplier search service (mostly: TLD filtering)."""
from __future__ import annotations

from app.services.search import _is_russian_domain


def test_accepts_ru_domains() -> None:
    assert _is_russian_domain("vseinstrumenti.ru")
    assert _is_russian_domain("dns-shop.ru")
    assert _is_russian_domain("shop.example.ru")


def test_accepts_idn_rf_domain_both_forms() -> None:
    # Unicode form
    assert _is_russian_domain("магазин.рф")
    # Punycode form (how httpx/urlparse may decode them)
    assert _is_russian_domain("xn--80aswg.xn--p1ai")


def test_accepts_su_domain() -> None:
    assert _is_russian_domain("retro.su")


def test_rejects_foreign_domains() -> None:
    assert not _is_russian_domain("amazon.com")
    assert not _is_russian_domain("ebay.com")
    assert not _is_russian_domain("alibaba.com")
    assert not _is_russian_domain("dhgate.com")
    assert not _is_russian_domain("homedepot.com")


def test_rejects_lookalike_subdomains_of_foreign_tld() -> None:
    # `ru.something.com` is NOT a .ru domain.
    assert not _is_russian_domain("ru.something.com")
    assert not _is_russian_domain("ru-shop.de")


def test_rejects_empty_and_garbage() -> None:
    assert not _is_russian_domain("")
    assert not _is_russian_domain("localhost")
    assert not _is_russian_domain(".")
