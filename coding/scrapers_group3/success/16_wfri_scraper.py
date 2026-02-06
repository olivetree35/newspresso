#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
우리금융연구소 (WFRI) 스크래퍼
- URL: https://www.wfri.re.kr/ko/web/research_report/research_report.php?search_type=list
- 구조: 목록 -> 상세 페이지 -> 첨부파일 다운로드 (Javascript onclick)
- 다운로드 로직: board_file_download('idx', 'board_code', 'file_cnt') 파싱 -> URL 조립
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
logger = logging.getLogger("WFRIScraper")

class WFRIScraper(AsyncBaseScraper):
    def __init__(self, start_date, end_date):
        super().__init__(start_date, end_date, site_name="우리금융연구소")
        self.base_url = "https://www.wfri.re.kr"
        # 초기 진입 URL
        self.target_url = "https://www.wfri.re.kr/ko/web/research_report/research_report.php?search_type=list"

    async def _scrape_board(self, page, url):
        """게시판 수집 (목록 -> 상세 진입 방식)"""
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(2000)
        
        collected_count = 0
        current_page = 1
        max_pages = 10 
        
        while current_page <= max_pages:
            logger.info(f"   📄 페이지 {current_page} 읽는 중...")
            
            # 목록 아이템 추출 (테이블 행 또는 리스트 아이템)
            # 구조 추정: .tbl-list tbody tr 또는 유사 구조
            items = await page.query_selector_all('tbody > tr, li.item, .list_box > li')
            
            if not items:
                logger.warning("   ⚠️ 목록 아이템을 찾을 수 없습니다.")
                break
                
            logger.info(f"   → 아이템 {len(items)}개 발견")
            
            page_collected = 0
            
            # 상세 페이지 이동을 위해 링크 요소들을 먼저 수집 (DOM 변경 방지 위해 href/onclick 정보 등 수집 필요하나, 상세 갔다가 back하면 element가 갱신됨)
            # 따라서 '하나씩' 처리하고 목록으로 '돌아오는' 방식 사용 (가장 안정적)
            
            # items는 handle이므로, 페이지를 벗어나면 효력을 잃을 수 있음.
            # 루프를 돌 때 매번 목록을 다시 잡거나, nth-child로 접근해야 함.
            
            # 전략: 현재 페이지의 아이템 개수만큼 반복하며 nth로 접근
            item_count = len(items)
            
            for i in range(item_count):
                try:
                    # 페이지가 리로드되었을 수 있으므로 다시 쿼리
                    current_items = await page.query_selector_all('tbody > tr, li.item, .list_box > li')
                    if i >= len(current_items):
                        break
                    
                    item = current_items[i]
                    
                    # 1. 날짜 추출 (목록에서 먼저 확인하여 Skip 여부 결정)
                    date_text = "0000-00-00"
                    
                    # 날짜 셀렉터 추정 (.date, td.date, td:nth-child...)
                    date_ele = await item.query_selector('.date, td.date, span.date')
                    # 만약 class가 없다면 <td> 중 날짜 형식이 있는 것 찾기
                    if not date_ele:
                        tds = await item.query_selector_all('td')
                        for td in tds:
                            txt = (await td.text_content()).strip()
                            if re.match(r'\d{4}[.-]\d{2}[.-]\d{2}', txt):
                                date_text = txt
                                break
                    else:
                        date_text = (await date_ele.text_content()).strip()
                        
                    date_text = date_text.replace('.', '-')
                    
                    # 기간 체크
                    if not self.is_in_period(date_text):
                        if date_text != "0000-00-00" and date_text < str(self.start_date):
                             # 날짜순 정렬이라고 가정하고, 시작일보다 이전이면 중단(옵션)
                             # 여기서는 안전하게 continue
                             pass
                        # continue # 상세 진입 전에 날짜로 거름 (효율성)
                        # 날짜가 없으면(0000-00-00) 일단 상세 들어가볼 수도 있음. 일단은 스킵 안함.
                    
                    if date_text != "0000-00-00" and not self.is_in_period(date_text):
                        logger.debug(f"      [Skip] 기간 밖: {date_text}")
                        continue

                    # 2. 제목 요소 찾기
                    title_ele = await item.query_selector('a.tbl-link, .title a, a')
                    if not title_ele:
                        continue
                        
                    title = (await title_ele.text_content()).strip()
                    logger.debug(f"   [{i+1}/{item_count}] 분석: {title} ({date_text})")
                    
                    # 3. 상세 페이지 진입
                    # 클릭 시 페이지 이동 발생
                    
                    # 클릭 전 href나 onclick 확인
                    # href가 있으면 새 탭으로 여는게 빠름 (뒤로가기보다)
                    # 사용자 정보: onclick="ajax_board_view_count('2568');" -> href="..." 도 같이 있을것임.
                    
                    # 새 탭 열기 시도 (Ctrl+Click)
                    # modifier key 사용이 지원됨
                    
                    # 하지만 href가 'javascript:...' 형식이면 새 탭이 안 열릴 수 있음.
                    # 일단 클릭하고 돌아오는 방식(go_back) 사용
                    
                    await title_ele.click()
                    await page.wait_for_load_state('networkidle', timeout=10000)
                    
                    # --- 상세 페이지 ---
                    
                    # 상세 페이지에서 날짜 다시 확인 (목록에 없었을 경우)
                    if date_text == "0000-00-00":
                        date_detail = await page.query_selector('.view-date, .date, .info')
                        if date_detail:
                            txt = await date_detail.text_content()
                            # 정규식으로 YYYY-MM-DD 추출
                            m = re.search(r'\d{4}[.-]\d{2}[.-]\d{2}', txt)
                            if m:
                                date_text = m.group(0).replace('.', '-')
                    
                    # 기간 재검증
                    if not self.is_in_period(date_text):
                        logger.debug("      [Skip-Detail] 기간 밖")
                        await page.go_back()
                        await page.wait_for_load_state('networkidle')
                        continue

                    # 4. 다운로드 URL 추출
                    # 요소: <a href="javascript:void(0);" onclick="board_file_download('2568','research_report','2')">
                    
                    doc_url = "N/A"
                    # onclick에 board_file_download가 있는 a 태그 찾기
                    down_btn = await page.query_selector('a[onclick*="board_file_download"]')
                    
                    if down_btn:
                        onclick_val = await down_btn.get_attribute('onclick')
                        # 파싱: board_file_download('2568','research_report','2')
                        # 홑따옴표 또는 쌍따옴표, 공백 유연하게 처리
                        m = re.search(r"board_file_download\(\s*['\"]?(.+?)['\"]?,\s*['\"]?(.+?)['\"]?,\s*['\"]?(.+?)['\"]?\s*\)", onclick_val)
                        if m:
                            idx = m.group(1)
                            board_code = m.group(2)
                            file_cnt = m.group(3)
                            
                            # URL 조립
                            # https://www.wfri.re.kr/module/lib/board_file_download.php?idx=2568&board_code=research_report&file_cnt=2
                            doc_url = f"{self.base_url}/module/lib/board_file_download.php?idx={idx}&board_code={board_code}&file_cnt={file_cnt}"
                        else:
                            logger.warning(f"      패턴 매칭 실패: {onclick_val}")
                    
                    if doc_url != "N/A":
                        logger.info(f"      ✅ 수집 성공: {title[:20]}... ({date_text})")
                        self.save_result(title, date_text, doc_url, page.url)
                        collected_count += 1
                        page_collected += 1
                    else:
                        logger.warning(f"      ⚠️ 다운로드 버튼 없음: {title}")

                    # 목록으로 복귀
                    await page.go_back()
                    await page.wait_for_load_state('networkidle')
                    
                except Exception as e:
                    logger.error(f"      ❌ 아이템 처리 중 오류: {e}")
                    # 혹시 상세페이지에 갇혔으면 복귀 시도
                    if "research_report.php" not in page.url or "view" in page.url:
                        try:
                            await page.go_back()
                            await page.wait_for_load_state('networkidle')
                        except:
                            pass
            
            # 페이지네이션 (다음 페이지)
            # <div class="paging"> ... <a href="..." class="next"></a>
            next_btn = await page.query_selector('.paging .next, .btn_next')
            if next_btn:
                logger.info("   ▶ 다음 페이지로 이동")
                await next_btn.click()
                await page.wait_for_load_state('networkidle')
                current_page += 1
            else:
                logger.info("   🏁 마지막 페이지")
                break
                
        return collected_count

    async def scrape(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            page = await context.new_page()
            
            logger.info(f"🚀 [우리금융연구소] 수집 시작 ({self.start_date} ~ {self.end_date})")
            
            try:
                await self._scrape_board(page, self.target_url)
            except Exception as e:
                logger.error(f"❌ 수집 중 치명적 오류: {e}")
            finally:
                await browser.close()
                

if __name__ == "__main__":
    # 윈도우 인코딩 설정
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except:
            pass

    import sys
    
    # 기본값
    start_date = None
    end_date = None
    
    # 1. 명령줄 인자 확인
    if len(sys.argv) >= 3:
        start_date = sys.argv[1]
        end_date = sys.argv[2]
    else:
        # 2. 대화형 입력
        print("\n[우리금융연구소 스크래퍼 실행]")
        try:
            input_start = input("수집 시작일 (YYYY-MM-DD) [엔터: 2024-01-01]: ").strip()
            if input_start:
                start_date = input_start
            else:
                start_date = "2024-01-01"
                
            input_end = input(f"수집 종료일 (YYYY-MM-DD) [엔터: 오늘]: ").strip()
            if input_end:
                end_date = input_end
            else:
                end_date = datetime.now().strftime("%Y-%m-%d")
        except KeyboardInterrupt:
            print("\n취소되었습니다.")
            sys.exit(0)
            
    # 실행
    scraper = WFRIScraper(start_date, end_date)
    asyncio.run(scraper.scrape())
    
    # 결과 저장 (단독 실행 시)
    if scraper.results:
        import json
        output_dir = os.path.join(cur_dir, "output")
        os.makedirs(output_dir, exist_ok=True)
        filename = f"wfri_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(scraper.results, f, ensure_ascii=False, indent=2)
        print(f"\n💾 결과 저장 완료: {filepath}")
    else:
        print("\n⚠️ 수집된 데이터가 없습니다.")
