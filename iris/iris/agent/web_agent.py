"""Playwright 웹 검색 (headless=False)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List
from urllib.parse import quote_plus


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str


def google_search_url(query: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(query)


def fetch_search_hits(query: str, max_results: int = 8) -> List[SearchHit]:
    """
    브라우저를 띄우고 검색 결과 수집.
    로그인/결제/개인정보 자동 입력은 하지 않음.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        return [
            SearchHit(
                "Playwright 미설치",
                "",
                f"pip install playwright 후 python -m playwright install chromium: {e}",
            )
        ]

    hits: List[SearchHit] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            page.goto(google_search_url(query), timeout=60000)
            page.wait_for_timeout(1500)
            for a in page.query_selector_all("a")[:40]:
                try:
                    href = a.get_attribute("href") or ""
                    text = (a.inner_text() or "").strip().replace("\n", " ")
                    if not href.startswith("http"):
                        continue
                    if "google.com" in href:
                        continue
                    if len(text) < 2:
                        continue
                    hits.append(SearchHit(title=text[:120], url=href, snippet=""))
                    if len(hits) >= max_results:
                        break
                except Exception:
                    continue
        finally:
            browser.close()

    if not hits:
        return [SearchHit("결과 없음", google_search_url(query), "검색 페이지를 확인해 주세요.")]
    return hits


def extract_query_from_text(text: str) -> str:
    """사용자 문장에서 검색어 추출 (간단)."""
    t = text.strip()
    for prefix in ("검색해줘", "검색 해줘", "웹 검색", "자료 찾아줘", "자료 찾아"):
        if t.startswith(prefix):
            t = t[len(prefix) :].strip(" :,.")
    t = re.sub(r"(요약해줘|보고서로\s*정리)", "", t).strip()
    return t or "Iris assistant"
