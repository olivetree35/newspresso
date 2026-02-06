#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국토연구원 (KRIHS) 통합 스크래퍼
- 자동으로 library (월간 국토) + press (보도자료) 순차 수집
- 하나의 JSON 파일로 저장
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
        self.start_date = self._parse_date(start_date)
        self.end_date = self._parse_date(end_date)
        self.results = []  # 모든 결과를 하나의 리스트에 저장
        
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
        """양쪽 카테고리 모두 수집"""
        logger.info("📦 국토연구원 데이터 수집 시작")
        logger.info(f"수집 기간: {self.start_date.strftime('%Y-%m-%d')} ~ {self.end_date.strftime('%Y-%m-%d')}\n")
        
        # 1. Library (월간 국토)
        logger.info("=" * 60)
        logger.info("1️⃣ 월간 국토 수집 시작")
        logger.info("=" * 60)
        await self.scrape_library()
        
        # 2. Press (보도자료)
        logger.info("\n" + "=" * 60)
        logger.info("2️⃣ 보도자료 수집 시작")
        logger.info("=" * 60)
        await self.scrape_press()
        
        # 최종 저장
        logger.info("\n" + "=" * 60)
        self.save_files()
        logger.info("✅ 모든 카테고리 수집 완료!")
        logger.info("=" * 60)

    # ==================== LIBRARY (월간 국토) ====================
    async def scrape_library(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()
            
            target_url = "https://www.krihs.re.kr/krihsLibraryArticle/articleList.es?mid=a10103010000&pub_kind=1"
            download_base_url = "https://library.krihs.re.kr"

            logger.info(f"🌐 접속 중: {target_url}")
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)
            
            # Select box 권호 목록 수집
            logger.info("🔍 권호 목록 분석 중...")
            options = await page.query_selector_all('#report_num_temp option')
            
            target_issues = []
            for opt in options:
                val = await opt.get_attribute('value')
                text = (await opt.text_content()).strip()
                if not val: continue
                
                # 날짜 파싱
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
                
                # URL 파라미터로 이동
                issue_url = f"{target_url}&report_num_temp={issue['value']}"
                await page.goto(issue_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                
                # 통권 다운로드
                info_area = await page.query_selector('.public .info')
                if info_area:
                    title_h2 = await info_area.query_selector('h2.tit')
                    main_title = (await title_h2.text_content()).strip() if title_h2 else issue['text']
                    
                    down_links = await info_area.query_selector_all('a[href*="viewCntAddDown"]')
                    for link in down_links:
                        href = await link.get_attribute('href')
                        match_url = re.search(r"'(/library/api/media[^']+)'", href)
                        if match_url:
                            url = urljoin(download_base_url, match_url.group(1))
                            logger.info(f"   ✅ 통권: {main_title[:30]}...")
                            self.results.append({
                                'source': 'KRIHS_LIBRARY',
                                'title': f"[통권] {main_title}",
                                'date': issue['date'],
                                'download_url': url,
                                'collected_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            })
                            break
                
                # 챕터
                rows = await page.query_selector_all('.public .list table tbody tr')
                for row in rows:
                    title_td = await row.query_selector('.txt_left')
                    if not title_td: continue
                    sub_title = (await title_td.text_content()).strip()
                    
                    view_btn = await row.query_selector('a[href*="viewCntAddDown"]')
                    if view_btn:
                        v_href = await view_btn.get_attribute('href')
                        match_v = re.search(r"'(/library/api/media[^']+)'", v_href)
                        if match_v:
                            url = urljoin(download_base_url, match_v.group(1))
                            logger.info(f"   ✅ 챕터: {sub_title[:20]}...")
                            self.results.append({
                                'source': 'KRIHS_LIBRARY',
                                'title': sub_title,
                                'date': issue['date'],
                                'download_url': url,
                                'collected_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            })
                
            await browser.close()

    # ==================== PRESS (보도자료) ====================
    async def scrape_press(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()
            
            target_url = "https://www.krihs.re.kr/board.es?mid=a10607000000&bid=0008"

            logger.info(f"🌐 접속 중: {target_url}")
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)
            
            page_num = 1
            
            while True:
                logger.info(f"📄 페이지 {page_num} 처리 중...")
                
                items_data = await self.collect_press_items(page)
                logger.info(f"   발견된 게시물: {len(items_data)}개")
                
                if not items_data:
                    logger.info("더 이상 게시물이 없습니다.")
                    break
                
                for item in items_data:
                    if self._is_in_period(item['date_obj']):
                        logger.info(f"   ✅ {item['title'][:30]}... ({item['date_str']})")
                        
                        # 상세 페이지
                        await page.goto(item['detail_url'], wait_until="domcontentloaded", timeout=30000)
                        await page.wait_for_timeout(1000)
                        
                        download_links = await page.query_selector_all('a.btn_line[href*="boardDownload"]')
                        if download_links:
                            for link in download_links:
                                href = await link.get_attribute('href')
                                if href:
                                    download_url = urljoin(self.base_url, href)
                                    logger.info(f"      📎 {download_url}")
                                    self.results.append({
                                        'source': 'KRIHS_PRESS',
                                        'title': item['title'],
                                        'date': item['date_str'],
                                        'download_url': download_url,
                                        'detail_url': item['detail_url'],
                                        'collected_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    })
                                    break  # 첫 번째 파일만 수집하고 종료
                        
                        # 목록으로 복귀
                        await page.go_back(wait_until="domcontentloaded", timeout=30000)
                        await page.wait_for_timeout(1000)
                
                next_btn = await page.query_selector('.paging a.next:not(.disabled)')
                if next_btn:
                    await next_btn.click()
                    await page.wait_for_timeout(2000)
                    page_num += 1
                else:
                    logger.info("마지막 페이지입니다.")
                    break
            
            await browser.close()

    async def collect_press_items(self, page):
        """보도자료 목록 수집"""
        items_data = []
        items = await page.query_selector_all('.tstyle_list tbody tr')
        
        for item in items:
            try:
                title_link = await item.query_selector('td.txt_left a')
                if not title_link: continue
                
                title = (await title_link.text_content()).strip()
                title = re.sub(r'새글\s*', '', title).strip()
                
                detail_url = await title_link.get_attribute('href')
                if detail_url:
                    detail_url = urljoin(self.base_url, detail_url)
                
                date_td = await item.query_selector('td[aria-label="등록일"]')
                if not date_td:
                    date_td = await item.query_selector('td:nth-child(5)')
                date_str = (await date_td.text_content()).strip() if date_td else ""
                
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
                    'date_str': date_str,
                    'date_obj': date_obj
                })
            
            except Exception as e:
                logger.warning(f"   ⚠️ 항목 수집 오류: {e}")
        
        return items_data

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
        json_path = os.path.join(self.output_dir, f"krihs_all_results_{timestamp}.json")
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(unique_results, f, ensure_ascii=False, indent=4)
        
        logger.info(f"💾 저장: {json_path} ({len(unique_results)}건)")

if __name__ == "__main__":
    print("=" * 60)
    print("국토연구원 (KRIHS) 통합 스크래퍼")
    print("=" * 60)
    
    # 사용법 체크
    if len(sys.argv) == 3:
        start_date, end_date = sys.argv[1], sys.argv[2]
    else:
        print("\n날짜 형식: YYYY-MM-DD (예: 2025-01-01)")
        start_date = input("시작 날짜를 입력하세요: ").strip()
        end_date = input("종료 날짜를 입력하세요: ").strip()
        
        if not start_date or not end_date:
            print("❌ 날짜를 입력해주세요.")
            sys.exit(1)
    
    print(f"\n수집 기간: {start_date} ~ {end_date}")
    print("=" * 60)
    print()
    
    scraper = KRIHSScraper(start_date, end_date)
    asyncio.run(scraper.scrape_all())
