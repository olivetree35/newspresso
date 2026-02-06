#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국토연구원 (KRIHS) 스크래퍼 (Playwright 버전)
- URL: https://www.krihs.re.kr/krihsLibraryArticle/articleList.es?mid=a10103010000&pub_kind=1
- 방식: Playwright로 JavaScript 실행 후 다운로드 링크 추출
"""

import sys
import os
import asyncio
import logging
import json
import re
from datetime import datetime
from urllib.parse import urljoin
from playwright.async_api import async_playwright

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("KRIHS")

class KRIHSScraper:
    def __init__(self, start_date=None, end_date=None):
        self.base_url = "https://www.krihs.re.kr"
        self.download_base_url = "https://library.krihs.re.kr"  # 다운로드 API 도메인
        self.target_url = "https://www.krihs.re.kr/krihsLibraryArticle/articleList.es?mid=a10103010000&pub_kind=1"
        
        self.start_date = self._parse_date(start_date)
        self.end_date = self._parse_date(end_date)
        
        self.results = []
        self.output_dir = os.path.join(os.path.dirname(__file__), "output")
        if not os.path.exists(self.output_dir):
             self.output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "output"))
        os.makedirs(self.output_dir, exist_ok=True)

    def _parse_date(self, date_str):
        if not date_str: return None
        try: return datetime.strptime(date_str, "%Y-%m-%d")
        except: return None

    def _is_in_period(self, date_obj):
        if not date_obj: return False
        if self.start_date and date_obj < self.start_date: return False
        if self.end_date and date_obj > self.end_date: return False
        return True

    async def scrape(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()

            logger.info(f"🌐 접속 중: {self.target_url}")
            await page.goto(self.target_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)
            
            # Select box 권호 목록 수집
            logger.info("🔍 권호 목록 분석 중...")
            options = await page.query_selector_all('#report_num_temp option')
            
            target_issues = []
            for opt in options:
                val = await opt.get_attribute('value')
                text = (await opt.text_content()).strip()
                if not val: continue
                
                # 날짜 파싱: "통권530호 (2025. 12.)"
                match = re.search(r'\((\d{4})\.\s*(\d{1,2})\.\)', text)
                if match:
                    year, month = match.groups()
                    dt = datetime(int(year), int(month), 1)
                    if self._is_in_period(dt):
                        target_issues.append({
                            'value': val,
                            'text': text,
                            'date': dt.strftime("%Y-%m-%d")
                        })
           
            logger.info(f"🎯 수집 대상: {len(target_issues)}개")
            
            for idx, issue in enumerate(target_issues):
                logger.info(f"[{idx+1}/{len(target_issues)}] {issue['text']}")
                await self.process_issue(page, issue)
                
            await browser.close()
            self.save_files()

    async def process_issue(self, page, issue):
        try:
            # URL 파라미터로 직접 이동
            issue_url = f"{self.target_url}&report_num_temp={issue['value']}"
            await page.goto(issue_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)  # JavaScript 실행 대기
            
            # 메인 통권 다운로드
            info_area = await page.query_selector('.public .info')
            if info_area:
                title_h2 = await info_area.query_selector('h2.tit')
                main_title = (await title_h2.text_content()).strip() if title_h2 else issue['text']
                
                # 다운로드 버튼: href="javascript:viewCntAddDown(...)"
                down_links = await info_area.query_selector_all('a[href*="viewCntAddDown"]')
                for link in down_links:
                    href = await link.get_attribute('href')
                    # href 예시: javascript:viewCntAddDown('1','a-1920796','/library/api/media?...')
                    match_url = re.search(r"'(/library/api/media[^']+)'", href)
                    if match_url:
                        url = urljoin(self.download_base_url, match_url.group(1))
                        logger.info(f"   ✅ 통권: {main_title[:30]}...")
                        self.add_result(f"[통권] {main_title}", issue['date'], url)
                        break  # 첫 번째만
            
            #디버깅: 첫 권호만 HTML 저장
            debug_file = 'debug_krihs_issue.html'
            if not os.path.exists(debug_file):
                html_content = await page.content()
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                logger.info(f"   🛠️ 디버그 HTML 저장")
            
            # 챕터 리스트
            rows = await page.query_selector_all('.public .list table tbody tr')
            for row in rows:
                title_td = await row.query_selector('.txt_left')
                if not title_td: continue
                sub_title = (await title_td.text_content()).strip()
                
                # 다운로드 버튼
                view_btn = await row.query_selector('a[href*="viewCntAddDown"]')
                if view_btn:
                    v_href = await view_btn.get_attribute('href')
                    match_v = re.search(r"'(/library/api/media[^']+)'", v_href)
                    if match_v:
                        url = urljoin(self.download_base_url, match_v.group(1))
                        logger.info(f"   ✅ 챕터: {sub_title[:20]}...")
                        self.add_result(sub_title, issue['date'], url)

        except Exception as e:
            logger.warning(f"   ⚠️ 에러: {e}")

    def add_result(self, title, date, url):
        self.results.append({
            'source': 'KRIHS',
            'title': title,
            'date': date,
            'download_url': url,
            'collected_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    def save_files(self):
        if not self.results:
            logger.warning("⚠️ 데이터 없음")
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = os.path.join(self.output_dir, f"krihs_results_{timestamp}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=4)
        logger.info(f"💾 저장: {json_path} ({len(self.results)}건)")

if __name__ == "__main__":
    if len(sys.argv) == 3:
        s, e = sys.argv[1], sys.argv[2]
        scraper = KRIHSScraper(s, e)
        asyncio.run(scraper.scrape())
    else:
        print("Usage: python 11_krihs_scraper.py start_date end_date")
