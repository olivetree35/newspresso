
import sys
import os
import asyncio
import re
from datetime import datetime
from urllib.parse import urljoin
from playwright.async_api import async_playwright

# 상위 폴더 경로 설정
cur_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(cur_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from base import AsyncBaseScraper

class IBKScraper(AsyncBaseScraper):
    def __init__(self, start_date, end_date):
        super().__init__(start_date, end_date, "IBK투자증권")
        # 주의: HTTPS가 아닌 HTTP로 접속해야 함
        self.base_url = "http://research.ibk.co.kr"
        self.pages = {
            "경제분석": "/research/board/economy-news/list",
            "투자전략": "/research/board/invest-strategy/list",
            "산업분석": "/research/board/industry/list", 
            "기업분석": "/research/board/company/list" 
        }

    async def _scrape_category(self, page, cat_name, url_path):
        full_url = urljoin(self.base_url, url_path)
        logger_prefix = f"   [{cat_name}]"
        print(f"{logger_prefix} 이동: {full_url}")
        
        try:
            # 페이지 이동
            await page.goto(full_url, wait_until='networkidle', timeout=30000)
        except Exception as e:
            print(f"{logger_prefix} ⚠️ 접속 실패: {e}")
            return 0

        collected_count = 0
        current_page = 1
        
        while True:
            print(f"{logger_prefix} 페이지 {current_page} 분석 중...")
            
            # 리스트 아이템 대기
            try:
                # .subject 클래스가 로드될 때까지 대기
                await page.wait_for_selector('.subject', timeout=5000)
            except:
                print(f"{logger_prefix} ⚠️ 목록을 찾을 수 없음 (또는 로딩 지연)")
                # '게시물 없음' 텍스트 확인 (페이지 소스 전체에서)
                content = await page.content()
                if "등록된 게시물이 없습니다" in content or "no data" in content:
                    print(f"{logger_prefix} 🏁 게시물 없음. 종료.")
                    break

            # 아이템 추출
            # 분석 결과 .subject가 10개 발견됨. 이를 포함하는 li 또는 tr을 찾음.
            # li 안에 subject가 있는 구조가 가장 유력함.
            items = await page.query_selector_all('li:has(.subject)')
            
            # 만약 li 구조가 아니라면 그냥 .subject를 가진 div 등을 찾음 (예비)
            if not items:
                items = await page.query_selector_all('tr:has(.subject)')
            if not items:
                # 최후의 수단: .subject 자체를 아이템으로 간주하고 부모/형제 탐색
                items = await page.query_selector_all('.subject')
                if items:
                     print(f"{logger_prefix} ℹ️ .subject 요소를 직접 순회합니다.")

            if not items:
                print(f"{logger_prefix} ⚠️ 아이템 0개. 종료.")
                break
                
            print(f"{logger_prefix} 아이템 {len(items)}개 발견")
            
            count_in_page = 0
            for item in items:
                try:
                    # 제목 추출. item 자체가 .subject일 수도 있고 컨테이너일 수도 있음
                    title_elem = await item.query_selector('a')
                    # 만약 item이 컨테이너라면 .subject a 를 찾아야 함
                    if await item.query_selector('.subject a'):
                        title_elem = await item.query_selector('.subject a')
                    
                    if not title_elem:
                        # 텍스트만 있는 경우? 
                        continue
                    
                    title = (await title_elem.text_content()).strip()
                    view_href = await title_elem.get_attribute('href')
                    
                    # 날짜 추출
                    # 같은 컨테이너 내의 .date 또는 .meta
                    # item이 .subject라면 부모로 올라가서 찾아야 할 수도 있음
                    date_text = "0000-00-00"
                    
                    # 1. 컨테이너 내부 검색
                    date_elem = await item.query_selector('.date, .meta, .regDate')
                    if not date_elem:
                         # 2. 형제 요소 검색 (item이 .subject인 경우) -> Playwright에서는 elementhandle에서 xpath .. 불가.
                         # 따라서 위에서 item을 잡을 때 컨테이너(li)를 잡는게 중요했음.
                         # 만약 item이 li라면 텍스트 전체에서 찾기
                         full_txt = await item.text_content()
                         m = re.search(r'(\d{4})[\.-](\d{2})[\.-](\d{2})', full_txt)
                         if m:
                             date_text = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                    
                    if date_elem and date_text == "0000-00-00":
                        txt = (await date_elem.text_content()).strip()
                        m = re.search(r'(\d{4})[\.-](\d{2})[\.-](\d{2})', txt)
                        if m:
                            date_text = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

                    # 날짜 필터링
                    if not self.is_in_period(date_text):
                        if date_text != "0000-00-00" and date_text < str(self.start_date):
                            pass 
                        continue

                    # PDF 다운로드 링크 추출
                    pdf_url = "N/A"
                    down_btn = await item.query_selector('a.file, a.btn-down, a[href*="download"], img[src*="pdf"]')
                    if down_btn:
                        # a 태그인지 img 태그인지 확인
                        tag_name = await down_btn.evaluate("el => el.tagName")
                        if tag_name == "IMG":
                             # 이미지를 감싸는 a 태그 찾기
                             parent_a = await down_btn.evaluate_handle("el => el.closest('a')")
                             if parent_a:
                                 href = await parent_a.get_attribute('href')
                                 if href: pdf_url = urljoin(self.base_url, href)
                        else:
                            href = await down_btn.get_attribute('href')
                            if href:
                                pdf_url = urljoin(self.base_url, href)

                    full_view_url = urljoin(self.base_url, view_href) if view_href else page.url
                    
                    if pdf_url != "N/A":
                        print(f"      ✅ 수집: {title[:15]}... ({date_text})")
                        self.save_result(title, date_text, pdf_url, full_view_url)
                        collected_count += 1
                        count_in_page += 1
                    
                except Exception as e:
                    print(f"      ⚠️ 항목 처리 중 에러: {e}")
                    continue
            
            # 페이지네이션 처리
            # .paging > a 
            next_page = current_page + 1
            
            # 숫자 버튼 클릭 시도 (텍스트로 매칭)
            # 정확히 숫자만 있는 링크 찾기
            next_btn = await page.query_selector(f'.paging a:text-is("{next_page}")')
            
            if not next_btn:
                # 다음 화살표 버튼 (보통 alt="다음" 이미지를 포함하거나 class가 next)
                next_btn = await page.query_selector('.paging a.next, .paging .btn_next')
                
            if not next_btn:
                print(f"{logger_prefix} 🏁 다음 페이지 버튼 없음 ({next_page}). 종료.")
                break
            
            try:
                await next_btn.click()
                await page.wait_for_load_state('networkidle')
                await page.wait_for_timeout(1000)
                current_page += 1
            except Exception as e:
                print(f"{logger_prefix} ⚠️ 페이지 이동 실패: {e}")
                break

        return collected_count

    async def scrape(self):
        async with async_playwright() as p:
            # 브라우저 런칭
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720},
                ignore_https_errors=True
            )
            page = await context.new_page()
            
            print(f"🚀 [IBK투자증권] 수집 시작 ({self.start_date} ~ {self.end_date})")
            
            total_count = 0
            for cat_name, path in self.pages.items():
                print(f"\n📂 카테고리 시작: {cat_name}")
                count = await self._scrape_category(page, cat_name, path)
                total_count += count
                
            print(f"\n🏁 [IBK투자증권] 전체 수집 완료: 총 {total_count}건")
            await browser.close()

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
        print("\n[IBK투자증권 스크래퍼 실행]")
        try:
            start_in = input("시작일 (YYYY-MM-DD) [기본: 2024-01-01]: ").strip()
            start_date = start_in if start_in else "2024-01-01"
            end_in = input("종료일 (YYYY-MM-DD) [기본: 오늘]: ").strip()
            end_date = end_in if end_in else datetime.now().strftime("%Y-%m-%d")
        except KeyboardInterrupt:
            sys.exit(0)
        
    scraper = IBKScraper(start_date, end_date)
    asyncio.run(scraper.scrape())
    
    if scraper.results:
        import json
        output_dir = os.path.join(cur_dir, "output")
        os.makedirs(output_dir, exist_ok=True)
        filename = f"ibk_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(scraper.results, f, ensure_ascii=False, indent=2)
        print(f"\n💾 결과 저장 완료: {filepath}")
    else:
        print("\n⚠️ 수집된 데이터가 없습니다.")
