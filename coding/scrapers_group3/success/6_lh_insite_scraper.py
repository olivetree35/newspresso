#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LH (인사이트) 스크래퍼
- URL: https://lhri.lh.or.kr/web/pblictn/PblictnList.do?menuIdx=346&pblictnCode=LH_INSITE
- 대상: LH 인사이트 (LHI)
- 방식: 목록에서 ID 추출 -> 상세 URL 구성 -> 상세 페이지에서 PDF 추출 (01_lh_focus_scraper.py 기반)
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

# 스크립트 위치를 기준으로 모듈 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir)) # success 폴더 안에 있다면 두 단계 위? 확인 필요
# 현재 파일 위치: d:\Antigravity\coding\scrapers_group3\success\06_lh_insite_scraper.py (예정)
# 하지만 지금은 d:\Antigravity\coding\에 생성할지 확인.
# 사용자 요청: "성공폴더로 이동" -> 일단 coding 폴더에 만들고 테스트 후 이동.

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("LH_Insite")

class LHInsiteScraper:
    def __init__(self, start_date=None, end_date=None):
        self.base_url = "https://lhri.lh.or.kr"
        self.target_url = "https://lhri.lh.or.kr/web/pblictn/PblictnList.do?menuIdx=346&pblictnCode=LH_INSITE"
        self.menu_idx = "346"
        self.pblictn_code = "LH_INSITE"
        
        self.start_date = self._parse_date(start_date)
        self.end_date = self._parse_date(end_date)
        
        self.results = []
        self.output_dir = os.path.join(os.path.dirname(__file__), "output")
        if not os.path.exists(self.output_dir):
             # 상위 output 폴더 찾기
             self.output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "output"))
             if not os.path.exists(self.output_dir):
                 self.output_dir = "output"
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
            browser = await p.chromium.launch(headless=True) # 테스트 후 True로 변경 가능
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            logger.info(f"🌐 접속 중: {self.target_url}")
            await page.goto(self.target_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)

            # 1. 목록 수집
            targets = []
            max_pages = 50 
            current_page = 1
            
            while current_page <= max_pages:
                logger.info(f"📄 페이지 {current_page} - 목록 분석 중...")
                
                rows = await page.query_selector_all('ul.journal-list > li')
                if not rows:
                    logger.warning("❌ 게시물 목록을 찾을 수 없습니다.")
                    break
                
                logger.info(f"   🔍 게시물 {len(rows)}개 발견")
                page_collected_count = 0
                
                for row in rows:
                    title_elem = await row.query_selector('.textbox .title a')
                    date_elem = await row.query_selector('.infolist .date span:nth-child(2)')
                    
                    if not title_elem or not date_elem: continue
                        
                    title_text = (await title_elem.text_content()).strip()
                    date_text = (await date_elem.text_content()).strip()
                    
                    if not self._is_in_period(date_text): continue
                        
                    onclick_attr = await title_elem.get_attribute("onclick")
                    if onclick_attr:
                        match = re.search(r"searchView\('(\d+)'\)", onclick_attr)
                        if match:
                            p_id = match.group(1)
                            # 인사이트용 상세 ULR 구성
                            detail_url = f"https://lhri.lh.or.kr/web/pblictn/PblictnView.do?menuIdx={self.menu_idx}&pblictnCode={self.pblictn_code}&pblictnId={p_id}"
                            targets.append({
                                'title': title_text,
                                'date': date_text,
                                'url': detail_url
                            })
                            page_collected_count += 1
                
                if page_collected_count == 0 and len(targets) > 0:
                     logger.info("   ⏹️ 날짜 범위 초과로 목록 수집 종료")
                     break

                # 페이지네이션
                try:
                    next_page = current_page + 1
                    next_btn = await page.query_selector(f'a[onclick*="fn_link_page({next_page})"]')
                    if not next_btn:
                        next_btn = await page.query_selector('a.next, a.btn-next')
                    
                    if next_btn:
                        await next_btn.click(force=True)
                        await page.wait_for_timeout(2000)
                        current_page += 1
                    else:
                        logger.info("   🏁 마지막 페이지 도달")
                        break
                except Exception as e:
                    logger.warning(f"페이지 이동 실패: {e}")
                    break

            # 2. 상세 수집
            logger.info(f"📋 총 {len(targets)}건의 상세 페이지 수집 시작...")
            
            for i, target in enumerate(targets, 1):
                try:
                    logger.info(f"   [{i}/{len(targets)}] 상세 분석: {target['title'][:20]}...")
                    await page.goto(target['url'], wait_until='domcontentloaded', timeout=15000)
                    
                    pdf_url = "N/A"
                    files = await page.query_selector_all('a[href*="FileDown"]')
                    if files:
                        href = await files[0].get_attribute('href')
                        if href:
                            pdf_url = urljoin(self.base_url, href)
                            logger.info(f"      📎 PDF 발견: {pdf_url}")
                    
                    self.results.append({
                        'source': 'LH_Insite',
                        'title': target['title'],
                        'date': target['date'],
                        'pdf_url': pdf_url, # page_url 제외
                        'collected_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    
                except Exception as e:
                    logger.error(f"   ⚠️ 상세 수집 에러: {e}")

            await browser.close()
            self.save_files()

    def save_files(self):
        if not self.results:
            logger.warning("⚠️ 저장할 데이터가 없습니다.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = os.path.join(self.output_dir, f"lh_insite_results_{timestamp}.csv")
        
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=self.results[0].keys())
            writer.writeheader()
            writer.writerows(self.results)
        logger.info(f"💾 CSV 저장 완료: {csv_path}")

        # JSON 저장 추가
        json_path = csv_path.replace('.csv', '.json')
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
        print("LH 인사이트 스크래퍼")
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
    scraper = LHInsiteScraper(start_date, end_date)
    asyncio.run(scraper.scrape())
