#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
서울연구원 (SI) 스크래퍼 - 최종 수정본
- URL: https://www.si.re.kr/bbs/list.do?key=2024100039
- 구조: li > .txt-wrap 안에 제목, 날짜, 다운로드 링크 모두 존재 (상세 이동 불필요)
- 선택자: li:has(.txt-wrap), .tit a, .date + span, a[href*="fileDown.do"]
"""

import sys
import os
import asyncio
import logging
import csv
import json
import re
from datetime import datetime
from urllib.parse import urljoin

from playwright.async_api import async_playwright

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("SI")

class SIScraper:
    def __init__(self, start_date=None, end_date=None):
        self.base_url = "https://www.si.re.kr"
        self.target_url = "https://www.si.re.kr/bbs/list.do?key=2024100039"
        
        self.start_date = self._parse_date(start_date)
        self.end_date = self._parse_date(end_date)
        
        self.results = []
        self.output_dir = os.path.join(os.path.dirname(__file__), "output")
        if not os.path.exists(self.output_dir):
             self.output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "output"))
             if not os.path.exists(self.output_dir):
                 self.output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "output"))
        os.makedirs(self.output_dir, exist_ok=True)

    def _parse_date(self, date_str):
        if not date_str: return None
        try: return datetime.strptime(date_str, "%Y-%m-%d")
        except: return None

    def _is_in_period(self, date_str):
        if not date_str: return False
        try:
            date_str = date_str.strip().replace('.', '-').replace('/', '-')
            match = re.search(r'\d{4}-\d{2}-\d{2}', date_str)
            if match:
                current_date = datetime.strptime(match.group(0), "%Y-%m-%d")
            else:
                return False
            if self.start_date and current_date < self.start_date: return False
            if self.end_date and current_date > self.end_date: return False
            return True
        except: return False

    async def scrape(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            logger.info(f"🌐 접속 중: {self.target_url}")
            await page.goto(self.target_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)

            max_pages = 20
            current_page = 1
            
            while current_page <= max_pages:
                logger.info(f"📄 페이지 {current_page} - 목록 분석 중...")
                
                # HTML 구조 분석에 따른 선택자 수정
                # 각 아이템은 li 태그이며 내부에 .txt-wrap 클래스를 가짐
                items = await page.query_selector_all('li:has(.txt-wrap)')
                
                if not items:
                    logger.warning("❌ 게시물을 찾을 수 없습니다.")
                    await page.screenshot(path="debug_si_final.png")
                    break
                
                logger.info(f"   🔍 게시물 {len(items)}개 발견")
                page_collected_count = 0
                
                for item in items:
                    # 제목 (.tit a)
                    title_elem = await item.query_selector('.tit a')
                    if not title_elem:
                         title_elem = await item.query_selector('.tit')
                    
                    if not title_elem: continue
                    title_text = (await title_elem.text_content()).strip()

                    # 날짜 (i.date + span)
                    date_text = "0000-00-00"
                    # .date 클래스를 가진 i 태그 형제 span
                    # 또는 .mid-txt 안의 텍스트에서 추출
                    mid_txt_elem = await item.query_selector('.mid-txt')
                    if mid_txt_elem:
                        txt = await mid_txt_elem.text_content()
                        # 2026-01-22 
                        match = re.search(r'\d{4}-\d{2}-\d{2}', txt)
                        if match:
                            date_text = match.group(0)
                        else:
                            match_dot = re.search(r'\d{4}\.\d{2}\.\d{2}', txt)
                            if match_dot:
                                date_text = match_dot.group(0).replace('.', '-')

                    if not self._is_in_period(date_text): continue
                    
                    # 다운로드 URL 추출
                    pdf_url = "N/A"
                    # .down-btn a[href*="fileDown.do"]
                    download_link = await item.query_selector('.down-btn a[href*="fileDown.do"]')
                    
                    if download_link:
                        href = await download_link.get_attribute('href')
                        if href:
                             pdf_url = urljoin(self.base_url, href)
                    
                    # 수집 확인
                    if pdf_url != "N/A":
                        logger.info(f"      ✅ 수집: {title_text[:15]}... ({date_text})")
                        self.results.append({
                            'source': 'SI',
                            'title': title_text,
                            'date': date_text,
                            'pdf_url': pdf_url,
                            'collected_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                        page_collected_count += 1
                
                # 페이지네이션
                # 정보가 없지만 보통 클릭 가능한 숫자나 다음 버튼
                # onclick="fn_egov_link_page(2)" 등
                try:
                    next_page = current_page + 1
                    # onclick에 next_page 숫자가 있는 a 태그
                    next_btn = await page.query_selector(f'a[onclick*="{next_page}"]:not(.first):not(.last)')
                    
                    # 없으면 href pageIndex
                    if not next_btn:
                        next_btn = await page.query_selector(f'a[href*="pageIndex={next_page}"]')
                    
                    # 그래도 없으면 class='next' 또는 텍스트 '>' 등
                    if not next_btn:
                        next_btn = await page.query_selector('a.next, a.btn_next, a[title="다음 페이지"]')

                    if next_btn:
                        await next_btn.click()
                        await page.wait_for_timeout(2000)
                        current_page += 1
                    else:
                        logger.info("   🏁 마지막 페이지 도달")
                        break
                except Exception as e:
                    logger.warning(f"페이지 이동 중 에러: {e}")
                    break

            await browser.close()
            self.save_files()

    def save_files(self):
        if not self.results:
            logger.warning("⚠️ 저장할 데이터가 없습니다.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = os.path.join(self.output_dir, f"si_results_{timestamp}.csv")
        json_path = os.path.join(self.output_dir, f"si_results_{timestamp}.json")
        
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=self.results[0].keys())
            writer.writeheader()
            writer.writerows(self.results)
            
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=4)
            
        logger.info(f"💾 JSON 저장 완료: {json_path}")

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
        print("서울연구원 (SI) 스크래퍼")
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
    scraper = SIScraper(start_date, end_date)
    asyncio.run(scraper.scrape())
