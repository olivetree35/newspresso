#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
대신증권 스크래퍼
- URL: https://money2.daishin.com/E5/ResearchCenter/Work/DW_ResearchReits.aspx...
- 구조: ASP.NET WebForms
- 특징: 첨부파일 버튼이 이미지(btn_file3.gif)이며, href에 다운로드 링크(filedownload.aspx?rowid=...)가 존재함.
"""

import sys
import os
import asyncio
import logging
import re
from datetime import datetime
from urllib.parse import urljoin
from playwright.async_api import async_playwright

# 상위 폴더(success)의 부모(scrapers_group3)에서 base.py를 찾기 위해 경로 추가
cur_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(cur_dir) # scrapers_group3
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

try:
    from success.base import AsyncBaseScraper
except ImportError:
    # run_standalone 등의 상황 고려
    sys.path.append(cur_dir)
    try:
        from base import AsyncBaseScraper
    except ImportError:
        print("❌ base.py를 찾을 수 없습니다.")
        sys.exit(1)

# 로깅 설정
logger = logging.getLogger("DaishinScraper")

class DaishinScraper(AsyncBaseScraper):
    def __init__(self, start_date, end_date):
        super().__init__(start_date, end_date, site_name="대신증권")
        # 리츠/부동산 섹션 URL
        self.target_url = "https://money2.daishin.com/E5/ResearchCenter/Work/DW_ResearchReits.aspx?m=10904&p=11112&v=11661"
        self.base_url = "https://money2.daishin.com"

    async def _scrape_board(self, page, url):
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(2000)
        
        collected_count = 0
        current_page = 1
        max_pages = 10 
        
        while current_page <= max_pages:
            logger.info(f"   📄 페이지 {current_page} 읽는 중...")
            
            # 1. 첨부파일 버튼 직접 탐색 (가장 확실한 지표)
            file_btns = await page.query_selector_all('img[src*="btn_file"]')
            
            if not file_btns:
                logger.warning("   ⚠️ 첨부파일 버튼(btn_file)을 찾을 수 없습니다.")
                # 디버깅: HTML 구조 확인
                # html = await page.content()
                # logger.info(f"HTML Dump (First 1000 chars): {html[:1000]}")
                break
                
            logger.info(f"   → 아이템(파일버튼) {len(file_btns)}개 발견")
            
            count_in_page = 0
            
            for btn_img in file_btns:
                try:
                    # 1. 제목, 날짜 추출 (img 태그의 alt 속성 활용)
                    alt_text = await btn_img.get_attribute('alt')
                    # 예: "[대신증권 나미선] 월간 일본 부동산 (2026년 01월)  다운로드"
                    
                    if not alt_text:
                        logger.warning("      alt 속성 없음")
                        continue

                    # 날짜 파싱 (alt 기준)
                    date_text = "0000-00-00"
                    # (\d{4})년 (\d{2})월
                    m_date = re.search(r'(\d{4})년\s*(\d{2})월', alt_text)
                    if m_date:
                        date_text = f"{m_date.group(1)}-{m_date.group(2)}-01" # 1일로 가정
                    else:
                        # 다른 날짜 패턴 시도 (YYYY.MM.DD)
                        m_date2 = re.search(r'(\d{4})[\.-](\d{2})[\.-](\d{2})', alt_text)
                        if m_date2:
                            date_text = f"{m_date2.group(1)}-{m_date2.group(2)}-{m_date2.group(3)}"

                    # 제목 파싱
                    # [...] ... 다운로드 패턴 제거
                    title = alt_text
                    if "다운로드" in title:
                        title = title.replace("다운로드", "")
                    title = title.strip()
                    
                    # 2. 다운로드 URL 추출 (이미지의 부모 a 태그)
                    pdf_url = "N/A"
                    
                    # 부모 a 태그 찾기
                    parent_link_handle = await btn_img.evaluate_handle('el => el.closest("a")')
                    parent_link = parent_link_handle.as_element() if parent_link_handle else None
                    
                    if parent_link:
                        href = await parent_link.get_attribute('href')
                        if href:
                            pdf_url = urljoin(self.base_url, href)
                    else:
                        # 혹시 부모가 아니라 근처에 있는 경우 (형제)
                        # 이 부분은 구조를 모르면 어려우나, 보통 a > img 구조임.
                        # 사용자 정보: 버튼클릭시 나오는 요소_<img> ...
                        # 클릭해서 다운로드된다면 onclick이나 부모 a가 있어야 함.
                        pass

                    # 3. 기간 체크 & 저장
                    if not self.is_in_period(date_text):
                        # 너무 과거 데이터면 스킵
                        if date_text != "0000-00-00" and date_text < str(self.start_date):
                             pass
                        continue
                    
                    if pdf_url != "N/A":
                        logger.info(f"      ✅ 수집: {title[:20]}... ({date_text})")
                        self.save_result(title, date_text, pdf_url, page.url)
                        collected_count += 1
                        count_in_page += 1
                    else:
                        logger.warning(f"      링크 찾기 실패: {title}")
                        
                except Exception as e:
                    logger.warning(f"      Item Error: {e}")
                    continue

            # 페이지네이션
            # <div class="paging"> ... <a ...>Next</a>
            # ASP.NET은 보통 1, 2, 3... 숫자 버튼과 이전/다음 화살표가 있음.
            # 다음 페이지 숫자를 찾거나 '다음' 이미지를 찾아야 함.
            
            # 다음 페이지 번호 계산
            next_page_num = current_page + 1
            
            # 1. 숫자 버튼 클릭 시도 (1 2 [3] 4 5 ...)
            # <a>2</a>
            next_btn = await page.query_selector(f'.paging a:text("{next_page_num}")')
            
            # 2. 없으면 '다음' 이미지/버튼 클릭 (10페이지 단위 넘어갈때)
            if not next_btn:
                # alt="다음" 또는 class="btn_next" 등
                next_btn = await page.query_selector('.paging a[href*="Next"], .paging .next, img[alt="다음"]')

            if next_btn:
                logger.info("   ▶ 다음 페이지 클릭")
                await next_btn.click()
                await page.wait_for_load_state('networkidle')
                await page.wait_for_timeout(2000) # ASP.NET postback 대기
                current_page += 1
            else:
                logger.info("   🏁 마지막 페이지")
                break
                
        return collected_count

    async def scrape(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            logger.info(f"🚀 [대신증권] 수집 시작 ({self.start_date} ~ {self.end_date})")
            try:
                await self._scrape_board(page, self.target_url)
            except Exception as e:
                logger.error(f"❌ 수집 중 오류: {e}")
            finally:
                await browser.close()

if __name__ == "__main__":
    if sys.platform == 'win32':
        try: sys.stdout.reconfigure(encoding='utf-8')
        except: pass

    import sys
    
    start_date = None
    end_date = None
    
    if len(sys.argv) >= 3:
        start_date = sys.argv[1]
        end_date = sys.argv[2]
    else:
        print("\n[대신증권 스크래퍼 실행]")
        try:
            start_in = input("시작일 (YYYY-MM-DD) [Default: 2024-01-01]: ").strip()
            start_date = start_in if start_in else "2024-01-01"
            
            end_in = input("종료일 (YYYY-MM-DD) [Default: 오늘]: ").strip()
            end_date = end_in if end_in else datetime.now().strftime("%Y-%m-%d")
        except:
            sys.exit(0)

    scraper = DaishinScraper(start_date, end_date)
    asyncio.run(scraper.scrape())
    
    # 결과 저장 (단독 실행 시)
    if scraper.results:
        import json
        out_dir = os.path.join(cur_dir, "output")
        os.makedirs(out_dir, exist_ok=True)
        fpath = os.path.join(out_dir, f"daishin_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(scraper.results, f, ensure_ascii=False, indent=2)
        print(f"\n💾 결과 저장: {fpath}")
    else:
        print("\n⚠️ 수집된 데이터 없음")
