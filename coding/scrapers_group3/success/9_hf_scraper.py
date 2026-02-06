#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
주택금융연구원 (HF) 스크래퍼 - 최종 수정본
- URL: https://researcher.hf.go.kr/researcher/sub02/sub02_05.do
- 구조: div.research-area 목록 -> 상세(mode=view) -> 다운로드(a.pdf)
- 날짜: .info02 텍스트 파싱
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
logger = logging.getLogger("HF")

class HFScraper:
    def __init__(self, start_date=None, end_date=None):
        self.base_url = "https://researcher.hf.go.kr/researcher/sub02/sub02_05.do"
        self.list_url = "https://researcher.hf.go.kr/researcher/sub02/sub02_05.do"
        
        self.start_date = self._parse_date(start_date)
        self.end_date = self._parse_date(end_date)
        
        self.results = []
        self.output_dir = os.path.join(os.path.dirname(__file__), "output")
        # 상위 output 폴더 찾기
        if not os.path.exists(self.output_dir):
             self.output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "output"))
             if not os.path.exists(self.output_dir): # 한 단계 더 위
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

            # 첫 접속
            current_url = self.list_url
            logger.info(f"🌐 접속 중: {current_url}")
            await page.goto(current_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)

            max_pages = 20
            current_page = 1
            
            # 페이지네이션 루프
            while current_page <= max_pages:
                logger.info(f"📄 페이지 {current_page} - 목록 분석 중...")
                
                # HTML 구조 분석 결과: div.research-area
                rows = await page.query_selector_all('div.research-area')
                
                if not rows:
                    logger.warning("❌ 게시물 목록을 찾을 수 없습니다.")
                    # 디버깅용 덤프
                    await page.screenshot(path="debug_hf_final.png")
                    break
                
                targets = []
                logger.info(f"   🔍 게시물 {len(rows)}개 발견")
                
                for row in rows:
                    # 제목: h4 a
                    title_elem = await row.query_selector('h4 a')
                    if not title_elem: continue
                    
                    title_text = (await title_elem.text_content()).strip()
                    detail_href = await title_elem.get_attribute('href')
                    # href="?mode=view..." -> base_url + href
                    if detail_href:
                         detail_url = urljoin(self.base_url, detail_href)
                    else:
                         continue
                    
                    # 날짜: .info02 텍스트에서 파싱
                    date_text = "0000-00-00"
                    info_elem = await row.query_selector('.info02')
                    if info_elem:
                        info_text = await info_elem.text_content()
                        # 2025-12-30 패턴 찾기
                        match_date = re.search(r'\d{4}-\d{2}-\d{2}', info_text)
                        if match_date:
                            date_text = match_date.group(0)
                    
                    if not self._is_in_period(date_text):
                        if date_text != "0000-00-00": 
                             continue
                        # 날짜 못찾았으면 일단 상세 가서 확인
                    
                    targets.append({
                        'title': title_text,
                        'date': date_text,
                        'url': detail_url
                    })

                # 상세 페이지 순회
                if targets:
                    logger.info(f"   📋 {len(targets)}개의 상세 페이지 분석 시작...")
                    for t in targets:
                        try:
                            # 탭을 쓰지 않고 goto로 이동
                            await page.goto(t['url'], wait_until='domcontentloaded')
                            
                            # PDF 링크 찾기 (사용자 정보: a.pdf href="?mode=download...")
                            pdf_url = "N/A"
                            download_link = await page.query_selector('a.pdf')
                            if not download_link:
                                download_link = await page.query_selector('a[href*="mode=download"]')
                            
                            if download_link:
                                href = await download_link.get_attribute('href')
                                if href:
                                    # href=?mode=download... -> list_url + href(query)
                                    pdf_url = urljoin(self.list_url, href)
                            
                            # 상세에서 날짜 다시 확인
                            if t['date'] == "0000-00-00":
                                page_text = await page.content()
                                match_date = re.search(r'\d{4}-\d{2}-\d{2}', page_text)
                                if match_date:
                                    t['date'] = match_date.group(0)
                                    if not self._is_in_period(t['date']):
                                        continue

                            if pdf_url != "N/A":
                                logger.info(f"      ✅ 수집: {t['title'][:20]}... ({t['date']})")
                                self.results.append({
                                    'source': 'HF',
                                    'title': t['title'],
                                    'date': t['date'],
                                    'pdf_url': pdf_url,
                                    'collected_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                })
                        except Exception as e:
                            logger.error(f"      ⚠️ 상세 페이지 에러: {e}")
                
                # 목록 페이지 복귀 (페이지네이션 이동을 위해)
                # offset 계산: current_page * 10 (1페이지=0~9, 2페이지=10~19로 가정 시)
                # 근데 1페이지(offset 0)가 기본. 2페이지는 offset 10일 것임.
                next_offset = current_page * 10
                next_page_url = f"{self.base_url}?article.offset={next_offset}&articleLimit=10"
                
                logger.info(f"   🔄 다음 페이지로 이동(URL Load): {next_page_url}")
                await page.goto(next_page_url, wait_until='domcontentloaded')
                
                # 페이지 이동 성공 여부 확인 (게시물 있는가?)
                check_rows = await page.query_selector_all('div.research-area')
                if not check_rows:
                    logger.info("   🏁 마지막 페이지 도달 (게시물 없음)")
                    break
                
                current_page += 1

            await browser.close()
            self.save_files()

    def save_files(self):
        if not self.results:
            logger.warning("⚠️ 저장할 데이터가 없습니다.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = os.path.join(self.output_dir, f"hf_results_{timestamp}.csv")
        json_path = os.path.join(self.output_dir, f"hf_results_{timestamp}.json")
        
        # CSV 저장
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=self.results[0].keys())
            writer.writeheader()
            writer.writerows(self.results)
        
        # JSON 저장
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
        print("주택금융연구원 (HF) 스크래퍼")
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
    scraper = HFScraper(start_date, end_date)
    asyncio.run(scraper.scrape())
