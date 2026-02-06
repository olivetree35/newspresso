#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
포스코경영연구원 (POSRI) 스크래퍼 - 최종 수정본
- URL: https://www.posri.re.kr/kor/bbs/report_list.do...
- 대상: 연구보고서 (이슈리포트)
- 구조: div.lst-customer-type1 > div.inner > div.item
- 수집: 제목, 날짜, PDF 다운로드 링크 (a.btn-txt-down 또는 a[href*='download.do'])
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
logger = logging.getLogger("POSRI")

class POSRIScraper:
    def __init__(self, start_date=None, end_date=None):
        self.base_url = "https://www.posri.re.kr"
        self.target_url = "https://www.posri.re.kr/kor/bbs/report_list.do?mmcd=2402221432440016120&cate=2403071010350015910"
        
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

            logger.info(f"🌐 접속 중: {self.target_url}")
            await page.goto(self.target_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)

            max_pages = 20
            current_page = 1
            
            while current_page <= max_pages:
                logger.info(f"📄 페이지 {current_page} - 목록 분석 중...")
                
                # HTML 구조 분석에 기반한 정확한 선택자
                items = await page.query_selector_all('.lst-customer-type1 .item, div.item.hv_type.sz2')
                
                if not items:
                    logger.warning("❌ 게시물을 찾을 수 없습니다.")
                    # 디버깅용 덤프
                    await page.screenshot(path="debug_posri_final.png")
                    break
                
                logger.info(f"   � 게시물 {len(items)}개 발견")
                page_collected_count = 0
                
                for item in items:
                    # 제목 (.h_1 a 또는 .h_1)
                    title_elem = await item.query_selector('.h_1 a')
                    if not title_elem:
                        title_elem = await item.query_selector('.h_1')
                        
                    if not title_elem: continue
                    title_text = (await title_elem.text_content()).strip()

                    # 날짜 (.info span 첫번째)
                    date_text = "0000-00-00"
                    info_spans = await item.query_selector_all('.info span')
                    if info_spans:
                        # 첫번째 span이 보통 날짜 (2026.01.21)
                        # 혹시 모르니 - 또는 . 이 있는 텍스트 찾기
                        for span in info_spans:
                            txt = (await span.text_content()).strip()
                            if re.search(r'\d{4}[\.-]\d{2}[\.-]\d{2}', txt):
                                date_text = txt
                                break

                    # 날짜 포맷 통일 (YYYY-MM-DD)
                    date_text = date_text.replace('.', '-')
                    match_date = re.search(r'\d{4}-\d{2}-\d{2}', date_text)
                    if match_date:
                        date_text = match_date.group(0)
                        
                    if not self._is_in_period(date_text): continue
                    
                    # 다운로드 URL 추출
                    # 사용자 요청: <a href="/download.do..." class="btn-txt-down">
                    pdf_url = "N/A"
                    download_link = await item.query_selector('a[href*="download.do"]')
                    
                    if download_link:
                        href = await download_link.get_attribute('href')
                        if href:
                            # href="/download.do..." -> 절대 경로 변환
                            pdf_url = urljoin(self.base_url, href)
                    
                    # 수집 확인
                    if pdf_url != "N/A":
                        logger.info(f"      ✅ 수집: {title_text[:20]}... ({date_text})")
                        self.results.append({
                            'source': 'POSRI',
                            'title': title_text,
                            'date': date_text,
                            'pdf_url': pdf_url,
                            'collected_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                        page_collected_count += 1
                
                # 결과가 없으면 종료 판단
                if page_collected_count == 0 and len(items) > 0:
                     logger.info("   ⏹️ 날짜 범위 초과(또는 해당 없음)로 종료 체크")
                     # 포스코는 최신순 나열이므로, 여기서 멈춰도 될지 판단은 유저 몫이나 일단 break
                     if self.results: # 이미 수집된게 있다면 날짜 지난거니 종료
                         break
                
                # 페이지네이션
                try:
                    next_page = current_page + 1
                    # onclick="fn_link_page(2)"
                    next_btn = await page.query_selector(f'a[onclick*="fn_link_page({next_page})"]')
                    
                    # 없으면 > 버튼
                    if not next_btn:
                        next_btn = await page.query_selector('.paging .next, a.btn-next')

                    if next_btn:
                        await next_btn.click()
                        await page.wait_for_timeout(2000)
                        current_page += 1
                    else:
                        logger.info("   🏁 마지막 페이지 도달")
                        break
                except Exception as e:
                    logger.warning(f"페이지 이동 중 에러/종료: {e}")
                    break

            await browser.close()
            self.save_files()

    def save_files(self):
        if not self.results:
            logger.warning("⚠️ 저장할 데이터가 없습니다.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = os.path.join(self.output_dir, f"posri_results_{timestamp}.csv")
        json_path = os.path.join(self.output_dir, f"posri_results_{timestamp}.json")
        
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
        print("포스코경영연구원 (POSRI) 스크래퍼")
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
    scraper = POSRIScraper(start_date, end_date)
    asyncio.run(scraper.scrape())
