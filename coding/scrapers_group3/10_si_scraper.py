#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
서울연구원 (SI) 스크래퍼
- URL: https://www.si.re.kr/bbs/list.do?key=2024100039
- 방식: Playwright를 이용한 직접 다운로드 (Referer/Cookie 문제 해결)
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
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
        # 도시계획/주택 필터(subject=003) 적용
        self.target_url = "https://www.si.re.kr/bbs/list.do?key=2024100039&subject=003"
        
        self.start_date = self._parse_date(start_date)
        self.end_date = self._parse_date(end_date)
        
        self.results = []
        self.output_dir = os.path.join(os.path.dirname(__file__), "output")
        # 상위 디렉토리(output) 구조 맞추기
        if not os.path.exists(self.output_dir):
             self.output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "output"))
             if not os.path.exists(self.output_dir):
                 self.output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "output"))
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 다운로드 폴더
        self.download_dir = os.path.join(self.output_dir, "downloads_si")
        os.makedirs(self.download_dir, exist_ok=True)

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
            browser = await p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                accept_downloads=True
            )
            page = await context.new_page()

            logger.info(f"🌐 접속 중: {self.target_url}")
            await page.goto(self.target_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)

            max_pages = 20
            current_page = 1
            
            while current_page <= max_pages:
                logger.info(f"📄 페이지 {current_page} - 목록 분석 중...")
                # 필터 적용 시 .result-list 클래스가 없을 수 있음. 범용적인 li:has(.txt-wrap) 사용
                items = await page.query_selector_all('li:has(.txt-wrap)')
                if not items:
                    # 폴백: 일반적인 보드 리스트
                    items = await page.query_selector_all('.board_list li')
                
                if not items:
                    logger.warning("❌ 게시물을 찾을 수 없습니다.")
                    await page.screenshot(path="debug_si_final.png")
                    with open("debug_si_final.html", "w", encoding="utf-8") as f:
                        f.write(await page.content())
                    break
                
                logger.info(f"   🔍 게시물 {len(items)}개 발견")
                page_collected_count = 0
                
                for item in items:
                    # 제목 (strong.tit 추가)
                    title_elem = await item.query_selector('strong.tit, h3, .subject, .title, a.sbj')
                    if not title_elem: continue
                    title_text = (await title_elem.text_content()).strip()

                    # 날짜 (i.date + span 우선)
                    date_text = "0000-00-00"
                    
                    # 1순위: i.date + span (2025-05-23)
                    date_elem = await item.query_selector('i.date + span')
                    if date_elem:
                        date_text = (await date_elem.text_content()).strip()
                    else:
                        # 2순위: .date, .reg_date (이 경우 '등록일'이 나올 수 있으니 주의)
                        date_elem = await item.query_selector('.date, .reg_date')
                        if date_elem:
                             txt = (await date_elem.text_content()).strip()
                             # '등록일' 텍스트면 무시하고 다음 정규식으로
                             if "등록" not in txt:
                                 date_text = txt

                    if date_text == "0000-00-00":
                        txt = await item.text_content()
                        match = re.search(r'\d{4}[\.-]\d{2}[\.-]\d{2}', txt)
                        if match:
                            date_text = match.group(0)

                    # 날짜 포맷팅
                    date_text = date_text.replace('.', '-')
                    match_date = re.search(r'\d{4}-\d{2}-\d{2}', date_text)
                    if match_date:
                        date_text = match_date.group(0)
                        
                    logger.info(f"      [DEBUG] 제목: {title_text[:20]}... | 날짜: {date_text}")

                    if not self._is_in_period(date_text): 
                        logger.info(f"      [SKIP] 기간 미해당: {date_text}")
                        continue
                    

                    # 다운로드 버튼 찾기
                    download_link = await item.query_selector('a[href*="fileDown.do"]')
                    
                    pdf_result = "N/A"
                    abs_dl_url = ""
                    
                    if download_link:
                        try:
                            # URL 및 헤더 정보 준비
                            dl_href = await download_link.get_attribute('href')
                            abs_dl_url = urljoin(page.url, dl_href)
                            
                            # 파일명 생성
                            safe_title = re.sub(r'[\\/*?:"<>|]', "", title_text)
                            safe_title = safe_title[:50] 
                            filename = f"[SI]_{date_text}_{safe_title}.pdf"
                            save_path = os.path.join(self.download_dir, filename)
                            
                            # 쿠키 가져오기 context.cookies()는 현재 url 기준
                            cookies = await context.cookies(self.target_url)
                            cookie_dict = {c['name']: c['value'] for c in cookies}
                            
                            # 헤더 설정 (Referer 필수)
                            headers = {
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                                "Referer": page.url
                            }

                            if os.path.exists(save_path) and os.path.getsize(save_path) > 1024:
                                logger.info(f"      ⏭️ 이미 존재함 (Skipping): {filename}")
                                pdf_result = save_path
                            else:
                                logger.info(f"      📥 직접 다운로드 시도: {filename}")
                                response = requests.get(abs_dl_url, headers=headers, cookies=cookie_dict, verify=False, stream=True, timeout=60)
                                if response.status_code == 200:
                                    # 내용이 에러페이지인지 확인 (HTML이면 실패)
                                    ct = response.headers.get('Content-Type', '').lower()
                                    if 'html' in ct:
                                        logger.warning("      ❌ 다운로드 실패 (HTML 응답 - 차단됨)")
                                        pdf_result = "DOWNLOAD_BLOCKED_HTML"
                                    else:
                                        with open(save_path, 'wb') as f:
                                            for chunk in response.iter_content(chunk_size=8192):
                                                f.write(chunk)
                                        logger.info("      ✅ 다운로드 성공")
                                        pdf_result = save_path
                                else:
                                    logger.warning(f"      ❌ HTTP 에러: {response.status_code}")
                                    pdf_result = f"HTTP_{response.status_code}"

                        except Exception as e:
                            logger.warning(f"      ❌ 다운로드 에러: {e}")
                            pdf_result = "DOWNLOAD_FAILED"
                    else:
                        logger.info("      Link 없음")

                    if pdf_result and "FAILED" not in pdf_result and "BLOCKED" not in pdf_result:
                        self.results.append({
                            'source': 'SI',
                            'title': title_text,
                            'date': date_text,
                            'local_path': pdf_result,
                            'download_url': abs_dl_url,
                            'referer': page.url,
                            'collected_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                        page_collected_count += 1
                
                # 페이지네이션
                try:
                    next_page = current_page + 1
                    # onclick="fn_egov_link_page(2)" 형식이 많음
                    next_btn = await page.query_selector(f'a[href*="pageIndex={next_page}"], a[onclick*="{next_page}"]')
                    
                    if not next_btn:
                         next_btn = await page.query_selector('a.next, a.btn_next')

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
            
        logger.info(f"💾 결과 저장 완료: {len(self.results)}건")
        logger.info(f"   - CSV: {csv_path}")
        logger.info(f"   - 파일위치: {self.download_dir}")

def get_user_date_range():
    print("\n[서울연구원 스크래퍼 설정]")
    today = datetime.now().strftime("%Y-%m-%d")
    s = input(f"시작 날짜 (엔터: 2024-01-01): ").strip()
    if not s: s = "2024-01-01"
    e = input(f"종료 날짜 (엔터: {today}): ").strip()
    if not e: e = today
    return s, e

if __name__ == "__main__":
    if len(sys.argv) == 3:
        s, e = sys.argv[1], sys.argv[2]
    else:
        s, e = get_user_date_range()
    
    scraper = SIScraper(s, e)
    asyncio.run(scraper.scrape())
