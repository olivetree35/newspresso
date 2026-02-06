#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Savills (세빌스) 스크래퍼
- URL: https://www.savills.co.kr/insight-and-opinion/research.aspx
- 방식: 목록 페이지에서 상세 링크 수집 후 상세 페이지에서 날짜/PDF 추출
"""

import sys
import os
import asyncio
import importlib
import logging
import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

# 상위 폴더 경로 설정 (base.py 호출용)
cur_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(cur_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

try:
    AsyncBaseScraper = importlib.import_module("base").AsyncBaseScraper
except Exception:
    try:
        AsyncBaseScraper = importlib.import_module(".base", package=__package__).AsyncBaseScraper
    except Exception:
        print("❌ base.py를 찾을 수 없습니다.")
        sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("SavillsScraper")


class SavillsScraper(AsyncBaseScraper):
    def __init__(self, start_date, end_date):
        super().__init__(start_date, end_date, "Savills")
        self.base_url = "https://www.savills.co.kr"
        self.target_url = (
            "https://www.savills.co.kr/insight-and-opinion/research.aspx?rc=Korea&p=&t=&f=date&q=&page=1"
        )
        self._seen_urls = set()

    def _build_page_url(self, page_num: int) -> str:
        parsed = urlparse(self.target_url)
        query = parse_qs(parsed.query)
        query["page"] = [str(page_num)]
        new_query = urlencode(query, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    def _normalize_date(self, text: str) -> str:
        if not text:
            return "0000-00-00"

        m = re.search(r"(20\d{2})[\.\-/]\s*(\d{1,2})[\.\-/]\s*(\d{1,2})", text)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

        m = re.search(r"(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", text)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

        months = "January|February|March|April|May|June|July|August|September|October|November|December"
        m = re.search(r"(" + months + r")\s+(\d{1,2}),\s+(20\d{2})", text, re.IGNORECASE)
        if m:
            try:
                dt = datetime.strptime(f"{m.group(1)} {m.group(2)}, {m.group(3)}", "%B %d, %Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                return "0000-00-00"

        return "0000-00-00"

    async def _extract_listing_links(self, page):
        anchors = await page.query_selector_all("a[href]")
        items = []

        for anchor in anchors:
            try:
                href = await anchor.get_attribute("href")
                if not href:
                    continue

                if href.startswith("javascript") or href.startswith("#"):
                    continue

                full_url = urljoin(self.base_url, href)
                if ".pdf" in full_url.lower():
                    continue

                if "savills.co.kr" not in full_url:
                    continue

                if "/insight-and-opinion/" not in full_url:
                    continue

                if full_url in self._seen_urls:
                    continue

                title_text = (await anchor.text_content()) or ""
                title_text = title_text.strip()
                if len(title_text) < 3:
                    title_text = full_url.split("/")[-1]

                self._seen_urls.add(full_url)
                items.append({
                    "title": title_text,
                    "url": full_url
                })
            except Exception:
                continue

        return items

    async def _extract_date_from_page(self, page) -> str:
        candidates = []
        for selector in ["time", ".date", ".article-date", ".publish-date", ".news-date"]:
            try:
                elem = await page.query_selector(selector)
                if elem:
                    candidates.append(await elem.text_content())
            except Exception:
                continue

        if not candidates:
            try:
                body_text = await page.inner_text("body")
                candidates.append(body_text[:2000])
            except Exception:
                return "0000-00-00"

        for text in candidates:
            date_text = self._normalize_date(text)
            if date_text != "0000-00-00":
                return date_text

        return "0000-00-00"

    async def _extract_pdf_from_page(self, page) -> str:
        pdf_url = "N/A"

        try:
            pdf_link = await page.query_selector(
                'a[href*=".pdf"], a:has-text("PDF"), a:has-text("Download"), a:has-text("다운로드")'
            )
            if pdf_link:
                href = await pdf_link.get_attribute("href")
                if href:
                    pdf_url = urljoin(page.url, href)
        except Exception:
            pass

        if pdf_url == "N/A" and self.recent_responses:
            for res_url in reversed(self.recent_responses):
                if ".pdf" in res_url.lower():
                    pdf_url = res_url
                    break

        return pdf_url

    async def _scrape_detail(self, context, item):
        detail_page = await context.new_page()
        detail_page.on("response", self._on_response)

        try:
            await detail_page.goto(item["url"], wait_until="domcontentloaded", timeout=30000)
            await detail_page.wait_for_timeout(2000)
            date_text = await self._extract_date_from_page(detail_page)
            pdf_url = await self._extract_pdf_from_page(detail_page)
            return date_text, pdf_url
        finally:
            await detail_page.close()

    async def scrape(self, page):
        collected = 0
        context = page.context
        max_pages = 5

        for page_num in range(1, max_pages + 1):
            list_url = self._build_page_url(page_num)
            logger.info(f"📄 Savills 페이지 {page_num} 접속: {list_url}")

            await page.goto(list_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            items = await self._extract_listing_links(page)
            if not items:
                logger.info("   ⚠️ 목록 항목 없음")
                break

            logger.info(f"   → 목록 {len(items)}개 발견")

            for item in items[:20]:
                try:
                    logger.info(f"   🔎 상세 수집 시도: {item['title'][:30]}...")
                    date_text, pdf_url = await self._scrape_detail(context, item)
                    logger.info(f"      → 날짜: {date_text}, PDF: {pdf_url}")

                    if date_text != "0000-00-00" and not self.is_in_period(date_text):
                        logger.info(f"      ⛔ 기간 제외: {date_text}")
                        continue

                    if pdf_url != "N/A" or date_text != "0000-00-00":
                        self.save_result(item["title"], date_text, pdf_url, item["url"])
                        collected += 1
                        logger.info(f"      ✅ 수집 성공: {item['title'][:20]}... ({date_text})")
                    else:
                        logger.warning(f"      ⚠️ 데이터 부족 (날짜: {date_text}, PDF: {pdf_url})")
                except Exception as e:
                    logger.error(f"      ❌ 상세 처리 오류: {e}")
                    continue

        return collected


async def run_scraper(start_date, end_date):
    scraper = SavillsScraper(start_date, end_date)
    async_playwright = importlib.import_module("playwright.async_api").async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 720}
        )
        page = await scraper._setup_page(context)

        try:
            await scraper.scrape(page)
        finally:
            await page.close()
            await context.close()
            await browser.close()

    if scraper.results:
        output_dir = os.path.join(cur_dir, "output")
        os.makedirs(output_dir, exist_ok=True)
        filename = f"savills_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(scraper.results, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 결과 저장: {filepath}")
    else:
        logger.warning("⚠️ 저장할 데이터가 없습니다.")


if __name__ == "__main__":
    if sys.platform == "win32":
        reconfigure = getattr(sys.stdout, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass

    if len(sys.argv) >= 3:
        start_date = sys.argv[1]
        end_date = sys.argv[2]
    else:
        print("\n[ Savills 스크래퍼 실행 ]")
        start_date = input("시작일 (YYYY-MM-DD) [기본: 2024-01-01]: ").strip() or "2024-01-01"
        end_date = input("종료일 (YYYY-MM-DD) [기본: 오늘]: ").strip() or datetime.now().strftime("%Y-%m-%d")

    asyncio.run(run_scraper(start_date, end_date))
