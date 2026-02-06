import asyncio
import os
import csv
import json
import logging
import re
import sys
import argparse
from datetime import datetime
from playwright.async_api import async_playwright

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class NICEScraper:
    def __init__(self, start_date: str, end_date: str):
        self.base_url = "https://www.nicerating.com"
        # '현행 평가방법론' 필터를 URL 파라미터로 직접 적용
        self.target_url = "https://www.nicerating.com/research/researchAll.do?fileTypM=230-1"
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d")
        self.end_date = datetime.strptime(end_date, "%Y-%m-%d")
        self.results = []
        
    def _is_in_period(self, date_str: str) -> bool:
        """날짜가 수집 기간 내인지 확인"""
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d")
            return self.start_date <= target_date <= self.end_date
        except:
            return False

    async def scrape(self):
        async with async_playwright() as p:
            # 브라우저 실행
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            logger.info(f"접속 중: {self.target_url}")
            await page.goto(self.target_url, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(3000)

            total_collected = 0
            max_pages = 10 # 최대 10페이지까지
            
            for current_page in range(1, max_pages + 1):
                logger.info(f"페이지 {current_page} 분석 중...")
                
                # 게시물 테이블 로딩 대기
                try:
                    await page.wait_for_selector('table.sortTable tbody tr', timeout=5000)
                except:
                    logger.info("게시물이 더 이상 없습니다 (Timeout).")
                    break
                
                rows = await page.query_selector_all('table.sortTable tbody tr')
                if not rows:
                    logger.info("게시물이 없습니다 (Empty rows).")
                    break

                page_count = 0
                for row in rows:
                    try:
                        # 제목 추출
                        title_elem = await row.query_selector("td.cell_type01 a")
                        if not title_elem:
                            continue
                        title = (await title_elem.text_content()).strip()

                        # 날짜 추출
                        date_str = "N/A"
                        tds = await row.query_selector_all('td')
                        for td in tds:
                            txt = (await td.text_content()).strip()
                            if re.match(r"\d{4}\.\d{2}\.\d{2}", txt): # 2026.01.28
                                date_str = txt.replace('.', '-')
                                break
                        
                        # 기간 필터
                        if self.end_date < datetime.strptime(date_str, "%Y-%m-%d"):
                            # 아직 기간 전임 (계속)
                            continue
                        if self.start_date > datetime.strptime(date_str, "%Y-%m-%d"):
                            # 기간 지남 (그만해도 되지만 순서 보장 안되면 계속)
                            logger.info(f"  [Skip] 날짜 범위 벗어남: {date_str}")
                            # 날짜순 정렬이라면 여기서 break 가능하지만 안전하게 continue for now
                            continue

                        # PDF URL 추출
                        row_html = await row.inner_html()
                        pdf_url = "N/A"
                        match = re.search(r"fncFileDown\(['\"]([^'\"]+)['\"]\)", row_html)
                        
                        if match:
                            doc_id = match.group(1)
                            pdf_url = f"https://www.nicerating.com/common/fileDown.do?docId={doc_id}"

                        # 결과 저장
                        self.results.append({
                            "title": title,
                            "date": date_str,
                            "link": pdf_url, 
                            "source": "NICE신용평가"
                        })
                        page_count += 1
                        total_collected += 1
                        logger.info(f"  [수집] {date_str} | {title[:30]}... | PDF: {bool(pdf_url!='N/A')}")

                    except Exception as e:
                        logger.error(f"  항목 처리 중 오류: {e}")

                if page_count == 0 and current_page > 1:
                    # 이번 페이지에서 수집한게 하나도 없으면 (날짜 필터 등으로)
                    # 만약 날짜 정렬이 되어있다면 종료해도 됨.
                    # 일단 계속 진행
                    pass

                # 다음 페이지 이동
                if current_page < max_pages:
                    try:
                        next_page = current_page + 1
                        
                        # goPage 함수 실행
                        logger.info(f"페이지 {next_page}로 이동 시도...")
                        await page.evaluate(f"if (typeof goPage === 'function') {{ goPage({next_page}); }}")
                        
                        # 로딩 대기
                        await page.wait_for_timeout(3000) 
                        
                    except Exception as e:
                        logger.error(f"페이지 이동 실패: {e}")
                        break
            
            await browser.close()
            logger.info(f"총 {total_collected}건 수집 완료")
            self.save_files()

    def save_files(self):
        if not self.results:
            logger.warning("저장할 데이터가 없습니다.")
            return

        # 디렉토리 생성
        output_dir = "scrapers_group3/output"
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # CSV 저장
        csv_filename = f"{output_dir}/nice_{timestamp}.csv"
        try:
            with open(csv_filename, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=["source", "title", "date", "link"])
                writer.writeheader()
                writer.writerows(self.results)
            logger.info(f"CSV 저장 완료: {csv_filename}")
        except Exception as e:
            logger.error(f"CSV 저장 실패: {e}")
            
        # JSON 저장
        json_filename = f"{output_dir}/nice_{timestamp}.json"
        try:
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, ensure_ascii=False, indent=2)
            logger.info(f"JSON 저장 완료: {json_filename}")
        except Exception as e:
            logger.error(f"JSON 저장 실패: {e}")

def main():
    if sys.platform == 'win32':
        try: sys.stdout.reconfigure(encoding='utf-8')
        except: pass

    import sys
    
    start_date = None
    end_date = None
    
    # 1. 명령줄 인자 확인
    if len(sys.argv) >= 3:
        start_date = sys.argv[1]
        end_date = sys.argv[2]
    else:
        # 2. 터미널 입력 지원
        print("\n" + "="*50)
        print("NICE 신용평가 스크래퍼 (Playwright)")
        print("="*50)
        
        try:
            start_in = input("시작일 (YYYY-MM-DD) [기본: 2024-01-01]: ").strip()
            start_date = start_in if start_in else "2024-01-01"
            
            end_in = input("종료일 (YYYY-MM-DD) [기본: 오늘]: ").strip()
            end_date = end_in if end_in else datetime.now().strftime("%Y-%m-%d")
        except KeyboardInterrupt:
            sys.exit(0)
        
    try:
        # 날짜 형식 검증
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        print(f"❌ 날짜 형식이 올바르지 않습니다: {start_date}, {end_date}")
        return

    print(f"\n📅 수집 기간: {start_date} ~ {end_date}")
    print("스크래핑을 시작합니다...\n")
    
    scraper = NICEScraper(start_date, end_date)
    asyncio.run(scraper.scrape())

if __name__ == "__main__":
    main()
