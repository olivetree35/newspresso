import asyncio
import os
import csv
import logging
import re
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
    def __init__(self):
        # '현행 평가방법론' 필터를 URL 파라미터로 직접 적용
        self.target_url = "https://www.nicerating.com/research/researchAll.do?fileTypM=230-1"
        self.results = []
        
    async def scrape(self):
        async with async_playwright() as p:
            # 브라우저 실행 (헤드리스 모드 해제하여 동작 확인 가능하게 함)
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
            max_pages = 5 # 테스트를 위해 최대 5페이지만 수집
            
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
                            if re.match(r"\d{4}\.\d{2}\.\d{2}", txt):
                                date_str = txt.replace('.', '-')
                                break

                        # PDF URL 추출 (fncFileDown 파싱)
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

                if page_count == 0:
                    logger.info("수집된 항목이 없어 종료합니다.")
                    break

                # 다음 페이지 이동
                if current_page < max_pages:
                    try:
                        next_page = current_page + 1
                        logger.info(f"페이지 {next_page}로 이동 시도...")
                        
                        # goPage 함수 실행
                        await page.evaluate(f"if (typeof goPage === 'function') {{ goPage({next_page}); }}")
                        
                        # 로딩 대기 (단순 대기)
                        await page.wait_for_timeout(3000) 
                        
                    except Exception as e:
                        logger.error(f"페이지 이동 실패: {e}")
                        break
            
            await browser.close()
            logger.info(f"총 {total_collected}건 수집 완료")
            self.save_to_csv()

    def save_to_csv(self):
        if not self.results:
            logger.warning("저장할 데이터가 없습니다.")
            return

        # 저장 경로 생성
        output_dir = "scrapers_group3/output" 
        os.makedirs(output_dir, exist_ok=True)
        filename = f"{output_dir}/nice_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        try:
            with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=["source", "title", "date", "link"])
                writer.writeheader()
                writer.writerows(self.results)
            logger.info(f"결과 저장 완료: {filename}")
        except Exception as e:
            logger.error(f"파일 저장 실패: {e}")

if __name__ == "__main__":
    scraper = NICEScraper()
    asyncio.run(scraper.scrape())
# 테스트
