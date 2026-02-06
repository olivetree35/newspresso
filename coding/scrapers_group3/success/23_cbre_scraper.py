import asyncio
import logging
import re
from datetime import datetime
from urllib.parse import urljoin
import os
import sys

# 상위 디렉토리의 base.py를 참조하기 위함 (또는 현재 폴더의 base.py)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from base import AsyncBaseScraper

# 로깅 설정
logger = logging.getLogger(__name__)

class CBREScraper(AsyncBaseScraper):
    def __init__(self, start_date=None, end_date=None):
        super().__init__(start_date, end_date)
        self.site_name = "CBRE"

    async def scrape(self):
        """
        CBRE 인사이트 수집 메인 로직
        """
        async with self._create_context() as context:
            collected = 0
            logger.info(f"[{self.site_name}] 수집 시작...")
            
            try:
                page = await context.new_page()
                # 1. 목록 페이지 접속
                url = "https://www.cbrekorea.com/insights"
                await page.goto(url, wait_until='networkidle', timeout=30000)
                await page.wait_for_timeout(3000)
                
                # 2. 리포트 상세 페이지 링크 수집 (/insights/reports/ 패턴)
                anchors = await page.query_selector_all("a[href*='/insights/reports/']")
                urls = []
                for a in anchors:
                    href = await a.get_attribute("href")
                    if href and href not in urls:
                        urls.append(urljoin(url, href))
                
                logger.info(f"   🔎 상세 링크 {len(urls)}개 발견")
                
                # 3. 각 상세 페이지 방문하여 데이터 추출
                for detail_url in urls[:20]: # 상위 20개 시도
                    try:
                        logger.info(f"      📖 상세 페이지 접속: {detail_url}")
                        await page.goto(detail_url, wait_until='networkidle', timeout=20000)
                        await page.wait_for_timeout(1000)
                        
                        # 제목 추출: h1
                        title = await page.inner_text("h1")
                        title = title.strip() if title else "No Title"
                        
                        # 날짜 추출: 본문에서 20XX 패턴 탐색
                        date_text = "0000-00-00"
                        body_text = await page.inner_text("body")
                        date_match = re.search(r'20\d{2}[.-]\d{1,2}[.-]\d{1,2}', body_text)
                        if date_match:
                            date_text = date_match.group(0).replace('.', '-')
                        
                        # 기간 필터링
                        if date_text != "0000-00-00" and not self.is_in_period(date_text):
                            logger.info(f"         ⛔ 기간 제외: {date_text}")
                            continue

                        # 다운로드 버튼 찾기 (a.cbre-c-download)
                        dl_button = await page.query_selector("a.cbre-c-download")
                        if dl_button:
                            pdf_url = await dl_button.get_attribute("href")
                            if pdf_url:
                                pdf_url = urljoin(detail_url, pdf_url.strip())
                                
                                # 결과 저장
                                self.save_result(title, date_text, pdf_url, detail_url)
                                collected += 1
                                logger.info(f"         ✅ 수집 성공: {title[:20]}... ({date_text})")
                            else:
                                logger.warning(f"         ⚠️ 다운로드 링크 href 없음")
                        else:
                            logger.warning(f"         ⚠️ 다운로드 버튼 미발견")
                            
                    except Exception as e:
                        logger.error(f"         ❌ 상세 처리 오류: {e}")
                        continue

            except Exception as e:
                logger.error(f"   ❌ {self.site_name} 전체 오류: {e}")
            finally:
                await page.close()
                
            return collected

if __name__ == "__main__":
    # Windows 한글 인코딩 설정
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    start_date = None
    end_date = None
    
    if len(sys.argv) >= 3:
        start_date = sys.argv[1]
        end_date = sys.argv[2]
    else:
        print(f"\n[ {CBREScraper().site_name} 스크래퍼 실행 ]")
        try:
            default_start = "2024-01-01"
            start_in = input(f"시작일 (YYYY-MM-DD) [기본: {default_start}]: ").strip()
            start_date = start_in if start_in else default_start
            
            end_in = input(f"종료일 (YYYY-MM-DD) [기본: 오늘]: ").strip()
            end_date = end_in if end_in else datetime.now().strftime("%Y-%m-%d")
        except KeyboardInterrupt:
            sys.exit(0)
    
    scraper = CBREScraper(start_date, end_date)
    asyncio.run(scraper.run())
