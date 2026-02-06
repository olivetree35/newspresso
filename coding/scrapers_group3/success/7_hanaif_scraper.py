"""
하나금융연구소 스크래퍼 (Playwright 버전)

수집 대상:
1. 연구보고서 (MN1000)
2. 하나금융포커스 (MN2000) - 사용자 요청 추가

특징: 
- onclick 이벤트(downloadItem) 파싱하여 PDF 링크 생성
- 2개 게시판 순차 수집
"""

import sys
import os

# 현재 파일의 디렉토리를 sys.path에 추가 (base 모듈 import 위함)
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from base import AsyncBaseScraper
import logging
import re
import asyncio
from urllib.parse import urljoin
from playwright.async_api import Page

# 로거 설정
logger = logging.getLogger("HanaIfScraper")

class HanaIfScraper(AsyncBaseScraper):
    def __init__(self, start_date, end_date):
        # 상속받은 클래스의 생성자 호출 시 site_name 전달
        super().__init__(start_date, end_date, site_name="하나금융연구소")
        self.site_name = "하나금융연구소"
        self.base_url = "https://www.hanaif.re.kr"

    def is_before_start_date(self, target_date_str: str) -> bool:
        """날짜 비교 헬퍼: 타겟 날짜가 시작일보다 이전인지 확인 (YYYY-MM-DD)"""
        # self.start_date가 datetime.date 객체일 수 있으므로 문자열로 변환하여 비교
        if not target_date_str or not self.start_date:
            return False
        return target_date_str < str(self.start_date)
        
    async def scrape(self, page: Page) -> int:
        total_collected = 0
        
        # 수집할 타겟 리스트 (순차 실행)
        targets = [
            {
                "name": "연구보고서",
                "url": f"{self.base_url}/boardList.do?menuId=MN1000&tabMenuId=N"
            },
            {
                "name": "하나금융포커스",
                "url": f"{self.base_url}/boardList.do?menuId=MN2000&tabMenuId=MN2100"
            }
        ]
        
        for target in targets:
            logger.info(f"==================================================")
            logger.info(f"   [{self.site_name}] '{target['name']}' 수집 시작")
            logger.info(f"   URL: {target['url']}")
            logger.info(f"==================================================")
            
            try:
                count = await self._scrape_board(page, target['url'], target['name'])
                total_collected += count
            except Exception as e:
                logger.error(f"   ❌ {target['name']} 수집 중 치명적 오류: {e}")
        
        return total_collected

    async def _scrape_board(self, page: Page, url: str, board_name: str) -> int:
        """개별 게시판 수집 로직"""
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(3000) # 로딩 대기 시간 증가
        
        collected_count = 0
        current_page = 1
        max_pages = 10 
        
        while current_page <= max_pages:
            logger.info(f"   📄 페이지 {current_page} 읽는 중...")
            
            # 리스트 아이템 추출 (다양한 선택자 시도)
            items = await page.query_selector_all('ul.listType01 > li')
            if not items:
                items = await page.query_selector_all('.board_list > li, .list_box > li, tbody > tr')
            
            if not items:
                logger.warning("   ⚠️ 게시글 목록을 찾을 수 없습니다. (HTML 구조 변경 가능성)")
                # 디버깅용: HTML 일부 출력
                # html = await page.content()
                # logger.debug(f"HTML Preview: {html[:500]}")
                break
                
            logger.info(f"   → 아이템 {len(items)}개 발견")
                
            page_collected = 0
            stop_signal = False
            
            for item in items:
                try:
                    # 1. 날짜 추출 및 기간 검증
                    date_ele = await item.query_selector('.date')
                    if not date_ele: 
                        print("      [DEBUG] [Skip] 날짜 요소 없음")
                        continue
                    
                    date_text = (await date_ele.text_content()).strip().replace('.', '-')
                    
                    # 기간 체크
                    if self.is_before_start_date(date_text):
                        print(f"      [DEBUG] [Stop] 날짜 지남: {date_text}")
                        stop_signal = True
                        break
                        
                    if not self.is_in_period(date_text):
                        print(f"      [DEBUG] [Skip] 기간 밖 데이터: {date_text}")
                        continue
                        
                    # 2. 제목 추출
                    title = "제목 없음"
                    # .hiddenEllips 또는 .tit 사용
                    hidden = await item.query_selector('.hiddenEllips')
                    if hidden:
                        title = await hidden.text_content()
                    else:
                        tit_ele = await item.query_selector('.tit')
                        if tit_ele:
                            title = await tit_ele.text_content()
                    title = title.strip()
                    print(f"      [DEBUG] 제목 추출: {title} ({date_text})")

                    # 3. 상세 URL (현재 페이지 URL 사용)
                    full_url = url
                    
                    # 4. 다운로드 URL 추출 (핵심)
                    download_url = "N/A"
                    # 선택자 확장: .fileBox a, 또는 .file a, 또는 onclick이 있는 아무 a 태그
                    file_btn = await item.query_selector('.fileBox a[onclick*="downloadItem"], .file a, a[onclick*="downloadItem"]')
                    
                    if file_btn:
                        onclick_text = await file_btn.get_attribute('onclick')
                        # downloadItem('36432', '102714') 패턴 파싱
                        m = re.search(r"downloadItem\(\s*['\"]?(\d+)['\"]?,\s*['\"]?(\d+)['\"]?\s*\)", onclick_text)
                        if m:
                            seq = m.group(2) 
                            download_url = f"{self.base_url}/dev/hanaifFileDownload.jsp?seq={seq}"
                        else:
                            # seq 하나만 있는 경우
                            m2 = re.search(r"downloadItem\(\s*['\"]?(\d+)['\"]?\s*\)", onclick_text)
                            if m2:
                                seq = m2.group(1)
                                download_url = f"{self.base_url}/dev/hanaifFileDownload.jsp?seq={seq}"
                    else:
                        print("      [DEBUG] [Skip] 다운로드 버튼 없음")
                    
                    if download_url != "N/A":
                        self.save_result(title, date_text, download_url, full_url)
                        logger.info(f"      ✅ 수집: {title[:20]}... ({date_text})")
                        collected_count += 1
                        page_collected += 1
                    else:
                        logger.warning(f"      ⚠️ 다운로드 URL 실패: {title}")
                    
                except Exception as e:
                    logger.warning(f"      ⚠️ 아이템 처리 에러: {e}")
            
            if stop_signal:
                logger.info("   🛑 시작일 이전 데이터 발견 - 수집 종료")
                break
                
            if page_collected == 0 and current_page > 1:
                # 데이터가 하나도 없고 첫 페이지가 아니면 종료 (빈 페이지일 가능성)
                if len(items) == 0:
                    break
            
            # 다음 페이지 이동
            current_page += 1
            # 페이지 이동 스크립트 실행: goPage(2);
            # 버튼 찾기: <div class="paging"> ... <a href="javascript:goPage(2);">...</a>
            next_btn = await page.query_selector(f'.paging a[href*="goPage({current_page})"]')
            
            if next_btn:
                await next_btn.click()
                await page.wait_for_timeout(1500) # 로딩 대기
            else:
                # 다음 페이지 버튼이 없으면 종료
                logger.info("   🚫 다음 페이지 버튼 없음 - 종료")
                break
                
        return collected_count

# 실행 블록
if __name__ == "__main__":
    import sys
    import asyncio
    
    # 윈도우 인코딩 설정
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except:
            pass
    
    start_date = None
    end_date = None
    
    if len(sys.argv) >= 3:
        start_date = sys.argv[1]
        end_date = sys.argv[2]
    else:
        print("\n[하나금융연구소 스크래퍼 실행]")
        try:
            start_date = input("수집 시작일 (YYYY-MM-DD): ").strip()
            if not start_date: start_date = "2024-01-01"
            
            end_date = input("수집 종료일 (YYYY-MM-DD): ").strip()
            if not end_date: 
                import datetime
                end_date = datetime.datetime.now().strftime("%Y-%m-%d")
        except KeyboardInterrupt:
            sys.exit(0)
            
    print(f"\n📅 기간: {start_date} ~ {end_date}")
    
    scraper = HanaIfScraper(start_date, end_date)
    
    # scrape_all()은 base.py에 없으므로 (이전 코드 참조), 
    # 직접 브라우저 띄우고 scrape 호출하는 로직 구현
    async def run_standalone():
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True) # 디버깅 시 False
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()
            await scraper.scrape(page)
            await browser.close()
            
    try:
        asyncio.run(run_standalone())
    except Exception as e:
        print(f"실행 오류: {e}")
