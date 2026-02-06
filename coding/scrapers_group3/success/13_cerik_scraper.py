#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
한국건설산업연구원 (CERIK) 통합 스크래퍼
- 시장전망: https://www.cerik.re.kr/material/prospect (건설시장, 부동산시장, 건설경기지수)
- 동향브리핑: https://www.cerik.re.kr/report/briefing#/
"""

import sys
import os
import asyncio
import logging
import json
import re
from datetime import datetime
from urllib.parse import urljoin, unquote
from playwright.async_api import async_playwright

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("CERIK")

class CERIKScraper:
    def __init__(self, start_date=None, end_date=None):
        self.base_url = "https://www.cerik.re.kr"
        self.prospect_url = "https://www.cerik.re.kr/material/prospect"
        self.briefing_url = "https://www.cerik.re.kr/report/briefing#/"
        
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

    async def scrape_all(self):
        """두 카테고리 순차 수집"""
        logger.info("📦 한국건설산업연구원 통합 수집 시작")
        logger.info(f"수집 기간: {self.start_date.strftime('%Y-%m-%d') if self.start_date else 'N/A'} ~ {self.end_date.strftime('%Y-%m-%d') if self.end_date else 'N/A'}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            
            # 1. 시장전망 수집
            await self.scrape_prospect(context)
            
            # 2. 동향브리핑 수집
            await self.scrape_briefing(context)
            
            await browser.close()
        
        self.save_files()
        logger.info("✅ 모든 카테고리 수집 완료!")

    async def scrape_prospect(self, context):
        """시장전망 수집 (건설시장, 부동산시장, 건설경기지수)"""
        logger.info("=" * 60)
        logger.info("📊 [시장전망] 수집 시작")
        
        page = await context.new_page()
        await page.goto(self.prospect_url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
        
        # 체크박스 선택
        for cb_id in ['inlineCheckbox1', 'inlineCheckbox2', 'inlineCheckbox3']:
            checkbox = await page.query_selector(f'#{cb_id}')
            if checkbox:
                is_checked = await checkbox.is_checked()
                if not is_checked:
                    await checkbox.click()
                    await page.wait_for_timeout(500)
        
        logger.info("   체크박스 선택 완료")
        await page.wait_for_timeout(2000)
        
        # 슬라이더 형식: .document-preview-item
        items = await page.query_selector_all('.document-preview-item')
        logger.info(f"   발견된 항목: {len(items)}개")
        
        collected = 0
        for item in items:
            try:
                # 제목
                title_elem = await item.query_selector('.title')
                title = (await title_elem.text_content()).strip() if title_elem else ""
                if not title: continue
                
                # 날짜 (.information 내 span)
                info_elem = await item.query_selector('.information')
                if info_elem:
                    info_text = await info_elem.text_content()
                    date_match = re.search(r'(\d{4})[-./](\d{1,2})[-./](\d{1,2})', info_text)
                else:
                    date_match = None
                
                if not date_match: continue
                
                date_str = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                
                if not self._is_in_period(date_obj): continue
                
                # PDF 링크
                pdf_link = await item.query_selector('a.btn-primary[href*="/uploads/report/"]')
                if not pdf_link: continue
                
                href = await pdf_link.get_attribute('href')
                if not href or '.pdf' not in href.lower(): continue
                
                pdf_url = f"{self.base_url}{href}" if href.startswith('/') else href
                
                logger.info(f"   ✅ {title[:40]}... ({date_str})")
                self.results.append({
                    'source': 'CERIK_PROSPECT',
                    'title': title,
                    'date': date_str,
                    'download_url': pdf_url,
                    'collected_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                collected += 1
            except Exception as e:
                continue
        
        logger.info(f"   시장전망 수집 완료: {collected}건")
        await page.close()

    async def scrape_briefing(self, context):
        """동향브리핑 수집"""
        logger.info("=" * 60)
        logger.info("📰 [동향브리핑] 수집 시작")
        
        page = await context.new_page()
        await page.goto(self.briefing_url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)
        
        # 슬라이더 형식: .document-preview-item
        items = await page.query_selector_all('.document-preview-item')
        logger.info(f"   발견된 항목: {len(items)}개")
        
        collected = 0
        for item in items:
            try:
                # 제목
                title_elem = await item.query_selector('.title')
                title = (await title_elem.text_content()).strip() if title_elem else ""
                if not title: continue
                
                # 날짜
                info_elem = await item.query_selector('.information')
                if info_elem:
                    info_text = await info_elem.text_content()
                    date_match = re.search(r'(\d{4})[-./](\d{1,2})[-./](\d{1,2})', info_text)
                else:
                    date_match = None
                
                if not date_match: continue
                
                date_str = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                
                if not self._is_in_period(date_obj): continue
                
                # PDF 링크
                pdf_link = await item.query_selector('a.btn-primary[href*="/uploads/report/"], a.btn-primary[href*=".pdf"]')
                if not pdf_link: continue
                
                href = await pdf_link.get_attribute('href')
                if not href: continue
                
                pdf_url = f"{self.base_url}{href}" if href.startswith('/') else href
                
                logger.info(f"   ✅ {title[:40]}... ({date_str})")
                self.results.append({
                    'source': 'CERIK_BRIEFING',
                    'title': title,
                    'date': date_str,
                    'download_url': pdf_url,
                    'collected_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                collected += 1
            except Exception as e:
                continue
        
        logger.info(f"   동향브리핑 수집 완료: {collected}건")
        await page.close()

    def save_files(self):
        """결과를 하나의 JSON 파일로 저장 (중복 제거)"""
        if not self.results:
            logger.warning("⚠️ 데이터 없음")
            return
        
        # download_url 기준 중복 제거
        seen_urls = set()
        unique_results = []
        for item in self.results:
            url = item['download_url']
            if url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(item)
        
        removed_count = len(self.results) - len(unique_results)
        if removed_count > 0:
            logger.info(f"🔄 중복 제거: {removed_count}건")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = os.path.join(self.output_dir, f"cerik_results_{timestamp}.json")
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(unique_results, f, ensure_ascii=False, indent=4)
        
        logger.info(f"💾 저장: {json_path} ({len(unique_results)}건)")

if __name__ == "__main__":
    if sys.platform == 'win32':
        try: sys.stdout.reconfigure(encoding='utf-8')
        except: pass

    start_date = None
    end_date = None
    
    if len(sys.argv) >= 3:
        start_date = sys.argv[1]
        end_date = sys.argv[2]
    else:
        print("\n" + "="*50)
        print("한국건설산업연구원 (CERIK) 스크래퍼")
        print("="*50)
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            start_in = input("시작일 (YYYY-MM-DD) [기본: 2024-01-01]: ").strip()
            start_date = start_in if start_in else "2024-01-01"
            
            end_in = input(f"종료일 (YYYY-MM-DD) [기본: {today}]: ").strip()
            end_date = end_in if end_in else today
        except KeyboardInterrupt:
            sys.exit(0)

    print(f"\n📅 수집 기간: {start_date} ~ {end_date}")
    scraper = CERIKScraper(start_date, end_date)
    asyncio.run(scraper.scrape_all())
