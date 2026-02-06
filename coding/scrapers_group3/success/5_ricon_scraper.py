#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
대한건설정책연구원(RICON) 스크래퍼
- URL: https://www.ricon.re.kr/board/list.php?group=issue&page=economic_index&cate=9
- 대상: 건설경제지표
- 날짜 필터링 지원: YYYY-MM-DD
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

from playwright.async_api import async_playwright, Page

# 스크립트 위치를 기준으로 모듈 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(os.path.join(current_dir, 'ricon_scraper.log'), encoding='utf-8'),
        logging.StreamHandler()  
    ]
)
logger = logging.getLogger("RICON")

class RICONScraper:
    def __init__(self, start_date=None, end_date=None):
        self.base_url = "https://www.ricon.re.kr"
        self.target_url = "https://www.ricon.re.kr/board/list.php?group=issue&page=economic_index&cate=9"
        
        self.start_date = self._parse_date(start_date)
        self.end_date = self._parse_date(end_date)
        
        self.results = []
        self.output_dir = os.path.join(project_root, "output")
        os.makedirs(self.output_dir, exist_ok=True)

    def _parse_date(self, date_str):
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            logger.error(f"❌ 날짜 형식 오류: {date_str} (YYYY-MM-DD 형식이어야 함)")
            return None

    def _is_in_period(self, date_str):
        if not date_str or date_str == "N/A":
            return False
            
        try:
            # 다양한 날짜 형식 지원
            date_str = date_str.strip().replace('.', '-').replace('/', '-')
            if "년" in date_str: # 2026년 1월 1일 처리
                result = re.search(r'(\d{4})[^0-9]+(\d{1,2})[^0-9]+(\d{1,2})', date_str)
                if result:
                    date_str = f"{result.group(1)}-{result.group(2).zfill(2)}-{result.group(3).zfill(2)}"
            
            # YYYY-MM-DD 추출
            match = re.search(r'\d{4}-\d{2}-\d{2}', date_str)
            if match:
                current_date = datetime.strptime(match.group(0), "%Y-%m-%d")
            else:
                return False
                
            if self.start_date and current_date < self.start_date:
                return False
            if self.end_date and current_date > self.end_date:
                return False
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ 날짜 파싱 실패 ({date_str}): {e}")
            return False

    async def scrape(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            logger.info(f"🌐 접속 중: {self.target_url}")
            await page.goto(self.target_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)

            total_collected = 0
            max_pages = 50 # 충분히 설정
            current_page = 1
            
            while current_page <= max_pages:
                logger.info(f"📄 페이지 {current_page} 분석 중...")
                
                # 게시물 리스트 수집
                rows = await page.query_selector_all('table tbody tr') # RICON은 table 구조
                if not rows:
                     rows = await page.query_selector_all('.board-list > li') # 백업
                
                if not rows:
                    logger.warning("❌ 게시물 목록을 찾을 수 없습니다.")
                    break
                
                logger.info(f"   🔍 게시물 {len(rows)}개 발견")
                page_collected_count = 0
                
                for row in rows:
                    try:
                        # 날짜 추출
                        date_text = "N/A"
                        date_elem = await row.query_selector('td:nth-child(3), .date, td.date')
                        if date_elem:
                            date_text = await date_elem.text_content()
                            
                        # 날짜가 내용에 숨어있을 경우 (모바일 뷰 등)
                        if "20" not in date_text:
                            text_all = await row.text_content()
                            match = re.search(r'20\d{2}[.-]\d{2}[.-]\d{2}', text_all)
                            if match:
                                date_text = match.group(0)

                        if not self._is_in_period(date_text):
                            continue
                            
                        # 제목 추출
                        title_elem = await row.query_selector('a')
                        if not title_elem:
                            continue
                        
                        title_text = (await title_elem.text_content()).strip()
                        href = await title_elem.get_attribute('href')
                        
                        if not href or "javascript" in href:
                            continue
                            
                        detail_url = urljoin(self.base_url, href)
                        
                        # --- 상세 페이지 수집 ---
                        pdf_url = await self._scrape_detail(context, detail_url)
                        
                    self.results.append({
                        'source': 'RICON',
                        'title': title_text,
                        'date': date_text,
                        # 'link': detail_url, (사용자 요청으로 제거)
                        'pdf_url': pdf_url,
                        'collected_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    
                    # 더블 https 체크 및 수정
                    if pdf_url.startswith('https://https://'):
                        pdf_url = pdf_url.replace('https://https://', 'https://')
                    
                    logger.info(f"   ✅ [수집] {date_text} | {title_text[:15]}... | PDF: {'O' if pdf_url != 'N/A' else 'X'}")
                    total_collected += 1
                    page_collected_count += 1
                    
                except Exception as e:
                    logger.error(f"   ⚠️ 항목 에러: {e}")
                    continue
                
                # 다음 페이지 이동
                if page_collected_count == 0 and len(self.results) > 0:
                     # 이번 페이지에서 수집된 게 없고 이미 수집된 결과가 있다면 종료 (날짜 범위 벗어남)
                     logger.info("   ⏹️ 날짜 범위 초과로 스크래핑 종료")
                     break

                # 페이지네이션 (다음 버튼 찾기)
                # Next button: btn_next or page=N
                try:
                    next_btn = await page.query_selector('a.btn_next, a.next')
                    if not next_btn:
                        # 숫자 버튼으로 이동 (현재+1 페이지)
                        next_btn = await page.query_selector(f'a[href*="page={current_page + 1}"]')
                    
                    if next_btn:
                        await next_btn.click(force=True) # force=True로 가려짐 방지
                        await page.wait_for_timeout(3000) # 페이지 로딩 대기
                        current_page += 1
                    else:
                        logger.info("   🏁 마지막 페이지 도달")
                        break
                except Exception as e:
                    logger.warning(f"   ⚠️ 페이지 이동 실패 (마지막일 수 있음): {e}")
                    break

            await browser.close()
            
            logger.info(f"\n🎉 총 {total_collected}건 수집 완료")
            self.save_files()

    async def _scrape_detail(self, context, url):
        """새 탭에서 상세 페이지 열고 PDF 링크 추출 (실제 다운로드 시도)"""
        page = await context.new_page()
        pdf_url = "N/A"
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            
            # 1. file_download.php 링크 찾기
            download_link = await page.query_selector('a[href*="file_download.php"]')
            
            # 2. 없다면 일반 PDF/다운로드 링크 찾기
            if not download_link:
                candidates = await page.query_selector_all('a[href]')
                for lnk in candidates:
                    txt = await lnk.text_content()
                    hr = await lnk.get_attribute('href')
                    if hr and not hr.startswith('javascript') and ('pdf' in txt.lower() or 'download' in hr.lower()):
                        download_link = lnk
                        break
            
            if download_link:
                # 1. 새 창(Popup) 감지 시도 (사용자 요구사항: 새로 뜨는 창의 URL)
                try:
                    async with page.expect_popup(timeout=5000) as popup_info:
                        await download_link.click()
                    
                    popup = await popup_info.value
                    # 리디렉션 가능성 고려하여 네트워크가 잠잠해질 때까지 대기
                    await popup.wait_for_load_state("networkidle")
                    
                    pdf_url = popup.url
                    # 사용자가 원하는 '새 창 URL'임을 명시
                    logger.info(f"   [성공] 새 창(Popup) 최종 URL 포착: {pdf_url}")
                    await popup.close()
                    
                except Exception:
                    # 2. 팝업 아니면 다운로드 이벤트 시도
                    try:
                         # 이미 클릭을 했을 수 있으니 다시 클릭 시도하지 않고 이벤트만 기다려보거나
                         # 클릭이 씹혔을 수 있으니 다시 시도
                         async with page.expect_download(timeout=3000) as download_info:
                             await download_link.click()
                         
                         download = await download_info.value
                         pdf_url = download.url
                         await download.cancel()
                         logger.info(f"   [다운로드 감지] URL: {pdf_url}")
                         
                    except Exception:
                         # 3. 모두 실패 시 href 백업
                         raw = await download_link.get_attribute('href')
                         if raw:
                             pdf_url = urljoin(self.base_url, raw)
                             logger.info(f"   [링크 추출(백업)] {pdf_url}")
                        
        except Exception as e:
            logger.debug(f"상세 수집 실패: {e}")
        finally:
            await page.close()
        return pdf_url

    def save_files(self):
        if not self.results:
            logger.warning("⚠️ 저장할 데이터가 없습니다.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # CSV 저장
        csv_filename = f"ricon_results_{timestamp}.csv"
        csv_path = os.path.join(self.output_dir, csv_filename)
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=self.results[0].keys())
            writer.writeheader()
            writer.writerows(self.results)
        logger.info(f"💾 CSV 저장 완료: {csv_path}")

        # JSON 저장
        json_filename = f"ricon_results_{timestamp}.json"
        json_path = os.path.join(self.output_dir, json_filename)
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
        print("대한건설정책연구원 (RICON) 스크래퍼")
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
    scraper = RICONScraper(start_date, end_date)
    asyncio.run(scraper.scrape())
