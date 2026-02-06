
import os
import sys
import asyncio
import re
import json
from urllib.parse import urljoin
from datetime import datetime
from playwright.async_api import async_playwright

# 상위 폴더(base.py가 있는 곳)를 sys.path에 추가
cur_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(cur_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from base import AsyncBaseScraper

class KyoboScraper(AsyncBaseScraper):
    def __init__(self, start_date, end_date):
        super().__init__(start_date, end_date, "교보리얼코")
        self.base_url = "https://www.kyoborealco.co.kr"
        self.target_url = "https://www.kyoborealco.co.kr/insight/marketreport"

    async def scrape(self):
        collected_count = 0
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            
            page = await context.new_page()
            print(f"🚀 [교보리얼코] 수집 시작 ({self.start_date} ~ {self.end_date})")
            
            try:
                # 1. 페이지 접속
                await page.goto(self.target_url, wait_until='networkidle', timeout=60000)
                await page.wait_for_timeout(3000) # 렌더링 대기
                
                # 2. 리스트 아이템 추출 시도 (tbody tr 또는 게시판 형태 추정)
                # 제공된 힌트: <a href="/insight/files/download?fileUid=...">
                # 전체 a 태그 스캔 후 리포트 항목으로 보이는 것들 필터링
                
                links = await page.query_selector_all('a[href*="/insight/files/download"]')
                print(f"   🔍 발견된 다운로드 링크 수: {len(links)}개")
                
                processed_urls = set()
                
                for link in links:
                    try:
                        download_href = await link.get_attribute('href')
                        full_download_url = urljoin(self.base_url, download_href)
                        
                        if full_download_url in processed_urls:
                            continue
                        
                        # 이 다운로드 버튼이 속한 '행(row)' 찾기
                        # 이 다운로드 버튼이 속한 '행(row)' 찾기
                        row = await link.evaluate_handle("el => el.closest('tr')")
                        if not row.as_element():
                            # print("   ⚠️ tr 없음, li 시도...")
                            # li만 잡으면 텍스트가 없으므로 그 부모인 ul을 시도
                            row = await link.evaluate_handle("el => el.closest('ul')")
                        
                        if not row.as_element():
                             # 그래도 없으면 div.item 시도
                             row = await link.evaluate_handle("el => el.closest('div.board_list_item, div.item')")
                        
                        if not row.as_element():
                             print("   ⚠️ 부모 요소(tr/ul/div) 찾기 실패")
                             continue

                            
                        title = "No Title"
                        date_text = "0000-00-00"
                        
                        # 3. 제목 및 날짜 추출
                        if row:
                            # JSHandle null check 및 텍스트 추출
                            row_text = await row.evaluate("el => el ? (el.innerText || el.textContent) : ''")
                            if not row_text or not row_text.strip():
                                # print("   ⚠️ 텍스트 없음 (Empty Text)")
                                continue
                            # print(f"Row Text: {row_text[:50]}...") # 디버그용

                            
                            # 날짜 추출 (YYYY.MM.DD)
                            date_match = re.search(r'20\d{2}[.-]\d{1,2}[.-]\d{1,2}', row_text)
                            if date_match:
                                date_str = date_match.group(0).replace('.','-')
                                date_text = date_str
                            
                            # 제목 추출 (날짜나 다운로드 등 제외한 나머지 텍스트)
                            # 보통 제목이 가장 긴 텍스트일 확률이 높음, 혹은 a 태그 텍스트
                            # 여기서는 row 전체 텍스트에서 날짜를 제외하고 정제하는 방식 사용
                            lines = row_text.split('\n')
                            for line in lines:
                                if len(line.strip()) > 5 and not re.search(r'20\d{2}[.-]', line):
                                    title = line.strip()
                                    break
                                    
                        # 4. 날짜 필터링
                        if not self.is_in_period(date_text):
                            if date_text != "0000-00-00":
                                continue

                        # 5. 저장
                        if full_download_url not in processed_urls:
                            print(f"      ✅ 수집: {title[:20]}... ({date_text})")
                            self.save_result(title, date_text, full_download_url, self.target_url)
                            processed_urls.add(full_download_url)
                            collected_count += 1
                            
                    except Exception as e:
                        print(f"      ⚠️ 항목 처리 중 에러: {e}")
                        continue
                        
            except Exception as e:
                print(f"❌ 수집 중 큰 에러 발생: {e}")
            
            # 결과 저장
            if self.results:
                output_dir = os.path.join(cur_dir, "output")
                os.makedirs(output_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"kyobo_results_{timestamp}.json"
                filepath = os.path.join(output_dir, filename)
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(self.results, f, ensure_ascii=False, indent=4)
                print(f"   💾 결과 저장 완료: {filepath}")
            else:
                print("   ⚠️ 수집된 데이터 없음 (Selector나 로직 점검 필요)")

            await browser.close()
            return collected_count

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
        print("\n[교보증권 스크래퍼 실행]")
        try:
            start_in = input("시작일 (YYYY-MM-DD) [기본: 2024-01-01]: ").strip()
            start_date = start_in if start_in else "2024-01-01"
            end_in = input("종료일 (YYYY-MM-DD) [기본: 오늘]: ").strip()
            end_date = end_in if end_in else datetime.now().strftime("%Y-%m-%d")
        except KeyboardInterrupt:
            sys.exit(0)

    scraper = KyoboScraper(start_date, end_date)
    asyncio.run(scraper.scrape())
