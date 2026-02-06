#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
현대경제연구원 (HRI) 스크래퍼
- 대상: 연구보고서 (경제, 산업경영, 통일경제)
- URL: https://www.hri.co.kr/kor/report/report.html?mode=1 (2, 3)
"""

import sys
import os
import asyncio
import logging
import json
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin
from playwright.async_api import async_playwright

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("HRI")

class HRIScraper:
    def __init__(self, start_date=None, end_date=None):
        self.base_url = "https://www.hri.co.kr"
        # mode=1: 경제, mode=2: 산업경영, mode=3: 통일경제
        self.modes = [
            (1, "경제"),
            (2, "산업경영"),
            (3, "통일경제")
        ]
        
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
        logger.info("📦 현대경제연구원 (HRI) 수집 시작")
        logger.info(f"수집 기간: {self.start_date.strftime('%Y-%m-%d') if self.start_date else 'N/A'} ~ {self.end_date.strftime('%Y-%m-%d') if self.end_date else 'N/A'}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            
            for mode, mode_name in self.modes:
                await self.scrape_category(context, mode, mode_name)
                
            await browser.close()
        
        self.save_files()
        logger.info("✅ HRI 수집 완료!")

    async def scrape_category(self, context, mode, mode_name):
        logger.info("=" * 60)
        logger.info(f"📊 [{mode_name}] 카테고리 수집 시작 (mode={mode})")
        
        page = await context.new_page()
        page_num = 1
        
        while True:
            url = f"{self.base_url}/kor/report/report.html?mode={mode}&page={page_num}"
            logger.info(f"   페이지 이동: {url}")
            
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
            except Exception as e:
                logger.error(f"   페이지 로드 실패: {e}")
                break
            
            items = await page.query_selector_all('a.item')
            if not items:
                logger.info("   더 이상 항목이 없습니다.")
                break
                
            logger.info(f"   발견된 항목: {len(items)}개")
            
            should_stop = False
            page_collected = 0
            
            # 현재 페이지의 항목들을 순회
            # 주의: 상세 페이지로 이동하면 목록 페이지 컨텍스트가 바뀌므로,
            # URL과 메타데이터만 먼저 추출하고 상세 페이지 방문은 별도로 하거나 새 탭을 사용해야 함.
            # 여기서는 목록에서 기본 정보를 먼저 추출.
            
            current_page_items = []
            
            for item in items:
                try:
                    # 상세 URL
                    href = await item.get_attribute('href')
                    if not href: continue
                    detail_url = urljoin(url, href)
                    
                    # 제목
                    title_elem = await item.query_selector('.tit .tit-text')
                    title = (await title_elem.text_content()).strip() if title_elem else ""
                    
                    # 날짜 (발간일 찾기)
                    date_val = None
                    info_lists = await item.query_selector_all('.info .list')
                    for info_item in info_lists:
                        tit_el = await info_item.query_selector('.info-tit')
                        if tit_el and "발간일" in (await tit_el.text_content()):
                            val_el = await info_item.query_selector('.info-text')
                            if val_el:
                                date_text = (await val_el.text_content()).strip()
                                # 날짜 파싱 (2026-01-02)
                                try:
                                    date_val = datetime.strptime(date_text, "%Y-%m-%d")
                                except:
                                    pass
                            break
                    
                    if not date_val: continue
                    
                    # 날짜 체크
                    if self.end_date and date_val > self.end_date:
                        continue # 아직 기간 전 (미래)
                    
                    if self.start_date and date_val < self.start_date:
                        should_stop = True # 과거 데이터 도달
                        break
                        
                    current_page_items.append({
                        'title': title,
                        'date': date_val,
                        'detail_url': detail_url
                    })
                    
                except Exception as e:
                    logger.error(f"   항목 파싱 에러: {e}")
                    continue
            
            # 추출된 항목들에 대해 상세 페이지 방문하여 PDF 링크 수집
            for item_data in current_page_items:
                pdf_url = await self.get_params_from_detail(context, item_data['detail_url'])
                if pdf_url:
                    date_str = item_data['date'].strftime("%Y-%m-%d")
                    logger.info(f"   ✅ {item_data['title'][:40]}... ({date_str})")
                    self.results.append({
                        'source': f'HRI_{mode_name}',
                        'title': item_data['title'],
                        'date': date_str,
                        'download_url': pdf_url,
                        'collected_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    page_collected += 1
                
            if should_stop:
                logger.info("   설정된 기간 이전의 데이터에 도달하여 수집을 종료합니다.")
                break
                
            if page_collected == 0 and len(current_page_items) == 0:
                 # 이번 페이지에서 유효한 날짜가 없으면서 should_stop도 안 걸렸다면? (전부 미래 날짜인 경우 등)
                 # 하지만 목록은 보통 최신순이므로, 전부 미래면 계속 진행해야 할 수도 있고, 전부 과거면 should_stop.
                 # HRI 리스트는 '발간일순' 정렬이 기본이므로,
                 # 첫 항목이 start_date보다 작으면(과거면) 종료가 맞음.
                 # 마지막 항목이 end_date보다 크면(미래면) 다음 페이지도 봐야 함.
                 pass

            page_num += 1
            await asyncio.sleep(1) # 부하 조절
            
        await page.close()

    async def get_params_from_detail(self, context, detail_url):
        """상세 페이지 -> 다운로드 팝업 -> 실제 PDF 링크 추출"""
        page = await context.new_page()
        try:
            # 1. 상세 페이지 이동
            await page.goto(detail_url, wait_until="networkidle", timeout=20000)
            
            # 2. 다운로드 팝업 링크 찾기
            download_btn = await page.query_selector('a.popup-link.link[href*="file-download.html"]')
            if not download_btn:
                return None
                
            popup_href = await download_btn.get_attribute('href')
            popup_url = urljoin(detail_url, popup_href)
            
            # 3. 팝업 페이지로 이동
            await page.goto(popup_url, wait_until="networkidle", timeout=20000)
            
            # 4. 실제 PDF 다운로드 링크 찾기
            # 사용자 제공: <a class="d-block link my-2" ...>
            real_download_link = await page.query_selector('a.d-block.link, a[href*=".pdf"], a[download]')
            
            if real_download_link:
                file_href = await real_download_link.get_attribute('href')
                if file_href:
                    # 상대 경로일 경우 처리 (/upload/...)
                    full_pdf_url = urljoin(self.base_url, file_href)
                    logger.info(f"   ✅ 다운로드 링크 추출 성공: {full_pdf_url}")
                    return full_pdf_url
            
            logger.warning(f"   ⚠️ 팝업 내 다운로드 링크를 찾지 못함: {popup_url}")
            return None
            
        except Exception as e:
            logger.error(f"   상세 페이지 에러 ({detail_url}): {e}")
            return None
        finally:
            await page.close()

    def save_files(self):
        if not self.results:
            logger.warning("⚠️ 데이터 없음")
            return
            
        # 중복 제거
        seen_urls = set()
        unique_results = []
        for item in self.results:
            url = item['download_url']
            if url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(item)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = os.path.join(self.output_dir, f"hri_results_{timestamp}.json")
        
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
        print("현대경제연구원 (HRI) 스크래퍼")
        print("="*50)
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            start_in = input("시작일 (YYYY-MM-DD) [기본: 2024-01-01]: ").strip()
            start_date = start_in if start_in else "2024-01-01"
            
            end_in = input(f"종료일 (YYYY-MM-DD) [기본: 오늘]: ").strip()
            end_date = end_in if end_in else today
        except KeyboardInterrupt:
            sys.exit(0)
            
    print(f"\n📅 수집 기간: {start_date} ~ {end_date}")
    scraper = HRIScraper(start_date, end_date)
    asyncio.run(scraper.scrape())
