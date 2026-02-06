from .base import AsyncBaseScraper
import logging
import re
from playwright.async_api import Page
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

class NICEScraper(AsyncBaseScraper):
    """
    [NICE신용평가] 데이터 스크래퍼
    
    수집 대상: 산업분석 게시판 (현행 평가방법론)
    수집 항목: 제목, 날짜, PDF 다운로드 URL
    """

    def __init__(self, start_date: str, end_date: str):
        super().__init__(start_date, end_date, "NICE신용평가")
        self.base_url = "https://www.nicerating.com"
        self.url = "https://www.nicerating.com/research/researchAll.do"
        
    async def scrape(self, page: Page) -> int:
        collected_count = 0
        try:
            logger.info(f"[{self.site_name}] 접속 중: {self.url}")
            await page.goto(self.url, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(3000)
            
            # 1. 구분 필터 적용 ("현행 평가방법론" = 230-1)
            logger.info("구분 필터 설정 중...")
            try:
                # 옵션 선택
                await page.select_option('select[name="fileTypM"]', "230-1")
                await page.wait_for_timeout(1000)
                
                # 검색 실행 (JavaScript 함수 직접 호출 시도 후 버튼 클릭)
                # NICE는 보통 fnSearch() 또는 form submit을 사용함
                logger.info("검색 실행 (필터 적용)...")
                
                # 첫 번째 게시물 제목 기억 (리로드 확인용)
                first_row = await page.query_selector("table.sortTable tbody tr td.cell_type01 a")
                old_first_title = await first_row.text_content() if first_row else ""
                
                # 검색 버튼 클릭 또는 JS 실행
                res = await page.evaluate("""
                    () => {
                        if (typeof fnSearch === 'function') {
                            fnSearch();
                            return true;
                        }
                        return false;
                    }
                """)
                
                if not res:
                    # JS 함수가 없으면 검색 버튼 클릭
                    await page.click('button.btn_search, a.btn_search, input[alt="검색"]')
                
                # 리스트가 갱신될 때까지 대기
                # (이전 첫 번째 제목과 달라지거나, 네트워크 유휴 상태 대기)
                try:
                    await page.wait_for_function(
                        f"document.querySelector('table.sortTable tbody tr td.cell_type01 a').innerText.trim() !== '{old_first_title}'",
                        timeout=10000
                    )
                except:
                    # 타임아웃 나면 단순히 wait
                    await page.wait_for_timeout(3000)
                    
                logger.info("✅ 필터 적용 및 리스트 갱신 완료")

            except Exception as e:
                logger.warning(f"⚠️ 필터 적용 실패: {e}")
            
            await page.wait_for_timeout(2000)

            # 2. 페이지네이션 순회
            max_pages = 5
            current_page = 1
            last_page_first_title = ""
            
            while current_page <= max_pages:
                logger.info(f"[{self.site_name}] 페이지 {current_page} 분석 중...")
                
                # 현재 페이지의 게시물 로딩 대기
                await page.wait_for_selector('table.sortTable tbody tr')
                
                rows = await page.query_selector_all('table.sortTable tbody tr')
                if not rows:
                    logger.info("게시물이 없습니다.")
                    break
                
                # 중복 페이지 체크 (페이지 이동 실패 확인용)
                current_first_title_elem = await rows[0].query_selector("td.cell_type01 a")
                current_first_title = await current_first_title_elem.text_content() if current_first_title_elem else ""
                
                if current_page > 1 and current_first_title == last_page_first_title:
                    logger.warning("⚠️ 페이지 이동 실패 (이전 페이지와 데이터 동일). 수집 종료.")
                    break
                
                last_page_first_title = current_first_title
                page_collected = 0
                
                for row in rows:
                    try:
                        # 제목
                        title_elem = await row.query_selector("td.cell_type01 a")
                        if not title_elem:
                            continue
                        title_text = (await title_elem.text_content()).strip()
                        
                        # 날짜
                        date_text = "N/A"
                        tds = await row.query_selector_all('td')
                        for td in tds:
                            txt = (await td.text_content()).strip()
                            if re.match(r"\d{4}\.\d{2}\.\d{2}", txt): # 2026.01.28
                                date_text = txt.replace('.', '-')
                                break
                        
                        # 날짜 필터
                        if date_text != "N/A" and not self.is_in_period(date_text):
                            continue
                        
                        # PDF URL 추출 (HTML 내 fncFileDown 파싱)
                        row_html = await row.inner_html()
                        pdf_url = "N/A"
                        
                        # NICE 패턴: fncFileDown('UUID')
                        match = re.search(r"fncFileDown\(['\"]([^'\"]+)['\"]\)", row_html)
                        
                        if match:
                            doc_id = match.group(1)
                            pdf_url = f"https://www.nicerating.com/common/fileDown.do?docId={doc_id}"
                            
                        # 결과 저장
                        self.save_result(title_text, date_text, pdf_url, self.url)
                        collected_count += 1
                        page_collected += 1
                        logger.info(f"   [수집] {date_text} | {title_text[:20]}... | PDF: {bool(pdf_url!='N/A')}")

                    except Exception as e:
                        logger.error(f"행 분석 에러: {e}")
                
                # 다음 페이지 이동 로직
                if current_page >= max_pages:
                    break
                
                if page_collected == 0 and current_page > 1:
                     # 이번 페이지에서 수집된 게 없으면 (날짜 범위 벗어남 등) 종료
                     break
                
                current_page += 1
                
                try:
                    logger.info(f"페이지 {current_page}로 이동 시도...")
                    
                    # 현재 첫 번째 제목 기억 (변경 확인용)
                    old_title = last_page_first_title
                    
                    # JS 함수 호출
                    await page.evaluate(f"if (typeof goPage === 'function') {{ goPage({current_page}); }}")
                    
                    # 내용이 바뀔 때까지 대기 (최대 10초)
                    try:
                        await page.wait_for_function(
                            f"document.querySelector('table.sortTable tbody tr td.cell_type01 a').innerText.trim() !== '{old_title}'",
                            timeout=10000
                        )
                    except:
                        logger.warning("페이지 이동 타임아웃 (내용 변경 감지 불가)")
                        
                    await page.wait_for_timeout(2000) # 추가 안정화
                    
                except Exception as e:
                    logger.error(f"페이지 이동 오류: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"전체 에러: {e}")
            
        return collected_count
