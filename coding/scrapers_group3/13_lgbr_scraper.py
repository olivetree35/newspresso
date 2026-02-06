#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LG경영연구원 (LGBR) 스크래퍼
- URL: https://www.lgbr.co.kr/economy/list.do
- 방식: fnView 호출 후 hidden input에서 PDF 경로 추출
"""

import sys
import os
import asyncio
import logging
import json
import re
from datetime import datetime
from playwright.async_api import async_playwright

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("LGBR")

class LGBRScraper:
    def __init__(self, start_date=None, end_date=None):
        self.base_url = "https://www.lgbr.co.kr"
        self.target_url = "https://www.lgbr.co.kr/economy/list.do"
        
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

            logger.info(f"🌐 LG경영연구원 접속: {self.target_url}")
            await page.goto(self.target_url, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(3000)
            
            # 게시물 목록
            items = await page.query_selector_all('.search_result ul li')
            logger.info(f"📄 발견된 항목: {len(items)}개")
            
            target_items = []
            for item in items:
                try:
                    link = await item.query_selector('a[href*="fnView"]')
                    if not link: continue
                    
                    href = await link.get_attribute('href')
                    id_match = re.search(r'fnView\((\d+)\)', href)
                    if not id_match: continue
                    item_id = id_match.group(1)
                    
                    title_elem = await item.query_selector('dd strong')
                    title = (await title_elem.text_content()).strip() if title_elem else ""
                    
                    info_elem = await item.query_selector('dd p')
                    info_text = (await info_elem.text_content()).strip() if info_elem else ""
                    date_match = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', info_text)
                    
                    if date_match:
                        date_str = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
                        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                        
                        if self._is_in_period(date_obj):
                            target_items.append({
                                'id': item_id,
                                'title': title,
                                'date': date_str
                            })
                except Exception as e:
                    continue
            
            logger.info(f"🎯 수집 대상: {len(target_items)}개")
            
            for idx, t_item in enumerate(target_items):
                logger.info(f"[{idx+1}/{len(target_items)}] {t_item['title'][:30]}...")
                
                # fnView 호출 (모달 열림)
                await page.evaluate(f"fnView({t_item['id']})")
                await page.wait_for_timeout(2000)
                
                # hidden input에서 PDF 경로 추출
                pdf_path = await page.evaluate("document.getElementById('popFileNm')?.value || ''")
                
                if pdf_path:
                    pdf_url = f"{self.base_url}{pdf_path}"
                    logger.info(f"   ✅ {pdf_url}")
                    self.results.append({
                        'source': 'LGBR',
                        'title': t_item['title'],
                        'date': t_item['date'],
                        'download_url': pdf_url,
                        'collected_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                else:
                    logger.warning(f"   ❌ PDF 경로 없음")
                
                # 모달 닫기
                close_btn = await page.query_selector('.report_popup .close')
                if close_btn:
                    await close_btn.click()
                    await page.wait_for_timeout(1000)
            
            logger.info(f"✨ 총 {len(self.results)}건 수집 완료")
            await browser.close()
            self.save_files()

    def save_files(self):
        if not self.results:
            logger.warning("⚠️ 저장할 데이터가 없습니다.")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = os.path.join(self.output_dir, f"lgbr_results_{timestamp}.json")
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=4)
        
        logger.info(f"💾 저장: {json_path} ({len(self.results)}건)")

if __name__ == "__main__":
    print("=" * 60)
    print("LG경영연구원 (LGBR) 스크래퍼")
    print("=" * 60)
    
    if len(sys.argv) == 3:
        start_date, end_date = sys.argv[1], sys.argv[2]
    else:
        print("\n날짜 형식: YYYY-MM-DD (예: 2025-01-01)")
        start_date = input("시작 날짜를 입력하세요: ").strip()
        end_date = input("종료 날짜를 입력하세요: ").strip()
        
        if not start_date or not end_date:
            print("❌ 날짜를 입력해주세요.")
            sys.exit(1)
            
    scraper = LGBRScraper(start_date, end_date)
    asyncio.run(scraper.scrape())
