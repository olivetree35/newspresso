#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국토연구원 (KRIHS) 보도자료 스크래퍼
- URL: https://www.krihs.re.kr/board.es?mid=a10607000000&bid=0008
- 방식: Playwright로 각 게시물 상세 페이지 진입 후 첨부파일 다운로드 URL 수집
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
logger = logging.getLogger("KRIHS_PRESS")

class KRIHSPressScraper:
    def __init__(self, start_date=None, end_date=None):
        self.base_url = "https://www.krihs.re.kr"
        self.target_url = "https://www.krihs.re.kr/board.es?mid=a10607000000&bid=0008"
        self.bid = "0008"
        
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

            logger.info(f"🌐 보도자료 페이지 접속: {self.target_url}")
            await page.goto(self.target_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)
            
            # 페이지네이션 처리
            page_num = 1
            total_collected = 0
            
            while True:
                logger.info(f"📄 페이지 {page_num} 처리 중...")
                
                # 현재 페이지의 게시물 목록 수집
                items_data = await self.collect_items_from_page(page)
                logger.info(f"   발견된 게시물: {len(items_data)}개")
                
                if not items_data:
                    logger.info("더 이상 게시물이 없습니다.")
                    break
                
                # 각 게시물 처리
                for item in items_data:
                    if self._is_in_period(item['date_obj']):
                        logger.info(f"   ✅ {item['title'][:30]}... ({item['date_str']})")
                        await self.process_detail_page(page, item)
                        total_collected += 1
                
                # 다음 페이지 확인
                next_btn = await page.query_selector('.paging a.next:not(.disabled)')
                if next_btn:
                    await next_btn.click()
                    await page.wait_for_timeout(2000)
                    page_num += 1
                else:
                    logger.info("마지막 페이지입니다.")
                    break
            
            logger.info(f"✅ 총 {total_collected}개 게시물 수집 완료")
            await browser.close()
            self.save_files()

    async def collect_items_from_page(self, page):
        """현재 페이지에서 게시물 정보만 수집 (상세 페이지 이동 전)"""
        items_data = []
        items = await page.query_selector_all('.tstyle_list tbody tr')
        
        for item in items:
            try:
                # 제목 및 링크
                title_link = await item.query_selector('td.txt_left a')
                if not title_link:
                    continue
                
                title = (await title_link.text_content()).strip()
                # <i class="xi-new"></i> 같은 아이콘 텍스트 제거
                title = re.sub(r'새글\s*', '', title).strip()
                
                detail_url = await title_link.get_attribute('href')
                if detail_url:
                    detail_url = urljoin(self.base_url, detail_url)
                
                # list_no 추출 (URL에서)
                list_no_match = re.search(r'list_no=(\d+)', detail_url) if detail_url else None
                list_no = list_no_match.group(1) if list_no_match else None
                
                # 날짜
                date_td = await item.query_selector('td[aria-label="등록일"]')
                if not date_td:
                    date_td = await item.query_selector('td:nth-child(5)')
                date_str = (await date_td.text_content()).strip() if date_td else ""
                
                # 날짜 파싱
                date_obj = None
                for fmt in ["%Y.%m.%d", "%Y-%m-%d"]:
                    try:
                        date_obj = datetime.strptime(date_str, fmt)
                        break
                    except:
                        pass
                
                items_data.append({
                    'title': title,
                    'detail_url': detail_url,
                    'list_no': list_no,
                    'date_str': date_str,
                    'date_obj': date_obj
                })
            
            except Exception as e:
                logger.warning(f"   ⚠️ 항목 수집 오류: {e}")
        
        return items_data

    async def process_detail_page(self, page, item_data):
        """상세 페이지에서 첨부파일 다운로드 링크 추출"""
        try:
            await page.goto(item_data['detail_url'], wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1000)
            
            # 첨부파일 다운로드 링크 찾기: <a class="btn_line" href="/boardDownload.es?...">
            download_links = await page.query_selector_all('a.btn_line[href*="boardDownload"]')
            
            if download_links:
                for link in download_links:
                    href = await link.get_attribute('href')
                    if href:
                        download_url = urljoin(self.base_url, href)
                        logger.info(f"      📎 {download_url}")
                        self.add_result(item_data['title'], item_data['date_str'], download_url, item_data['detail_url'])
            else:
                logger.info(f"      ⚠️ 첨부파일 없음")
        
        except Exception as e:
            logger.warning(f"      ⚠️ 상세 페이지 오류: {e}")

    def add_result(self, title, date, download_url, detail_url):
        self.results.append({
            'source': 'KRIHS_PRESS',
            'title': title,
            'date': date,
            'download_url': download_url,
            'detail_url': detail_url,
            'collected_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    def save_files(self):
        if not self.results:
            logger.warning("⚠️ 데이터 없음")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = os.path.join(self.output_dir, f"krihs_press_results_{timestamp}.json")
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=4)
        
        logger.info(f"💾 저장: {json_path} ({len(self.results)}건)")

if __name__ == "__main__":
    print("=" * 60)
    print("국토연구원 (KRIHS) 보도자료 스크래퍼")
    print("=" * 60)
    
    if len(sys.argv) == 3:
        # Command line arguments 사용
        start_date, end_date = sys.argv[1], sys.argv[2]
    else:
        # Interactive 입력
        print("\n날짜 형식: YYYY-MM-DD (예: 2025-01-01)")
        start_date = input("시작 날짜를 입력하세요: ").strip()
        end_date = input("종료 날짜를 입력하세요: ").strip()
        
        if not start_date or not end_date:
            print("❌ 날짜를 입력해주세요.")
            sys.exit(1)
    
    print(f"\n수집 기간: {start_date} ~ {end_date}")
    print("=" * 60)
    print()
    
    scraper = KRIHSPressScraper(start_date, end_date)
    asyncio.run(scraper.scrape())
