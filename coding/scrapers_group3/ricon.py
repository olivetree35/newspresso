from .base import AsyncBaseScraper
import logging
import re
import asyncio
from datetime import datetime
from playwright.async_api import Page
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

class RICONScraper(AsyncBaseScraper):
    """
    [대한건설정책연구원] 데이터 스크래퍼
    
    특징: 
    - 첨부파일 클릭 시 새 창이 열리는 경우 핸들링
    - 상세 페이지 진입 후 PDF 추출
    """

    def __init__(self, start_date: str, end_date: str):
        super().__init__(start_date, end_date, "대한건설정책연구원")
        self.base_url = "https://www.ricon.re.kr"
        # 동향분석 > 건설경제지표 (cate=9)
        self.url = "https://www.ricon.re.kr/board/list.php?group=issue&page=economic_index&cate=9"
        
    async def scrape(self, page: Page) -> int:
        collected_count = 0
        current_page = 1
        max_pages = 5
        
        try:
            logger.info(f"[{self.site_name}] 접속 중: {self.url}")
            await page.goto(self.url, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(3000)
            
            while current_page <= max_pages:
                logger.info(f"[{self.site_name}] 페이지 {current_page} 분석 중...")
                
                # 게시물 목록 식별 (관대한 선택자)
                # 보통 table tr 또는 ul li 구조
                rows = await page.query_selector_all('table tbody tr, .board_list li, .list_box li')
                
                if not rows:
                    # div 형태일 수도 있음
                    rows = await page.query_selector_all('.board-list > li')
                
                if not rows:
                    logger.warning("게시물 목록을 찾을 수 없습니다. (선택자 확인 필요)")
                    # 디버깅용: body 텍스트 일부 출력
                    body_text = await page.text_content('body')
                    logger.debug(f"Body text start: {body_text[:100]}")
                    break
                
                logger.info(f"게시물 {len(rows)}개 발견")
                
                page_collected = 0
                
                for i, row in enumerate(rows):
                    try:
                        # 1. 날짜 추출 (필터링을 위해 먼저)
                        date_text = "N/A"
                        date_elem = await row.query_selector('.date, span.date, td:nth-child(3), td.date') # 일반적인 날짜 위치
                        
                        if date_elem:
                            date_text = await date_elem.text_content()
                            date_text = date_text.strip().replace('.', '-').replace('/', '-')
                            # YYYY-MM-DD 형식 추출
                            match = re.search(r'\d{4}-\d{2}-\d{2}', date_text)
                            if match:
                                date_text = match.group(0)
                        
                        # 날짜가 없으면 내용에서 찾아봄
                        if date_text == "N/A":
                            text = await row.text_content()
                            match = re.search(r'\d{4}-\d{2}-\d{2}', text)
                            if match:
                                date_text = match.group(0) # 2026-01-01
                            else:
                                match = re.search(r'\d{4}\.\d{2}\.\d{2}', text)
                                if match:
                                    date_text = match.group(0).replace('.', '-')

                        # 기간 필터
                        if date_text != "N/A":
                            if not self.is_in_period(date_text):
                                continue
                        
                        # 2. 제목 및 상세 링크 추출
                        title_elem = await row.query_selector('a') # 행 전체가 링크일 수도 있고 제목만일 수도 있음
                        if not title_elem:
                            title_elem = await row.query_selector('.subject, .title')
                            
                        if not title_elem:
                            continue
                            
                        title_text = (await title_elem.text_content()).strip()
                        
                        # 상세 페이지 이동을 위한 링크
                        link_elem = await row.query_selector('a[href*="view"], a[href*="read"]')
                        if not link_elem:
                            link_elem = await row.query_selector('a')
                            
                        if not link_elem:
                            continue
                            
                        # 상세 페이지 URL (새 탭에서 열기 위해)
                        href = await link_elem.get_attribute('href')
                        if not href or href.startswith('#') or href.startswith('javascript'):
                            continue
                            
                        full_url = urljoin(self.url, href)
                        
                        # --- 상세 페이지 진입 ---
                        detail_url = urljoin(self.url, href)
                        
                        # 새 탭 생성하여 이동 (안정성 확보)
                        new_page = await page.context.new_page()
                        try:
                            # 1. 상세 페이지 로드
                            await new_page.goto(detail_url, wait_until='domcontentloaded', timeout=15000)
                            
                            # 2. 다운로드 링크 클릭 및 최종 URL 추출
                            pdf_url = "N/A"
                            
                            # 패턴: file_download.php?type=board&no=XXXX&idx=0
                            download_link = await new_page.query_selector('a[href*="file_download.php"]')
                            
                            if download_link:
                                # 1. 새 창(Popup) 감지 시도
                                try:
                                    async with new_page.expect_popup(timeout=5000) as popup_info:
                                        await download_link.click()
                                    
                                    popup = await popup_info.value
                                    await popup.wait_for_load_state("networkidle")
                                    pdf_url = popup.url
                                    logger.info(f"   [성공] 새 창(Popup) 최종 URL: {pdf_url}")
                                    await popup.close()
                                    
                                except Exception:
                                    # 2. 팝업 아니면 다운로드 이벤트 시도
                                    try:
                                         async with new_page.expect_download(timeout=3000) as download_info:
                                             await download_link.click()
                                         
                                         download = await download_info.value
                                         pdf_url = download.url
                                         await download.cancel()
                                         logger.info(f"   [다운로드 감지] URL: {pdf_url}")
                                         
                                    except Exception:
                                         # 3. 모두 실패 시 href 백업
                                         raw_href = await download_link.get_attribute('href')
                                         if raw_href:
                                             pdf_url = urljoin(self.base_url, raw_href)

                            else:
                                # 백업: 'pdf' 또는 '다운로드' 텍스트를 가진 링크
                                backup_links = await new_page.query_selector_all('a')
                                for lnk in backup_links:
                                    txt = await lnk.text_content()
                                    h = await lnk.get_attribute('href')
                                    # javascript: 로 시작하지 않는 유효한 링크만
                                    if h and not h.startswith('javascript') and ('pdf' in txt.lower() or 'download' in h.lower()):
                                        # 여기서도 클릭해서 다운로드 URL을 얻어볼 수 있음
                                        try:
                                            async with new_page.expect_download(timeout=5000) as download_info:
                                                await lnk.click()
                                            download = await download_info.value
                                            pdf_url = download.url
                                            await download.cancel()
                                            break
                                        except:
                                            pdf_url = urljoin(self.base_url, h)
                                            break
                            
                            # 결과 저장
                            if pdf_url != "N/A":
                                self.save_result(title_text, date_text, pdf_url, detail_url)
                                collected_count += 1
                                page_collected += 1
                                logger.info(f"   [수집] {date_text} | {title_text[:20]}... | PDF: O")
                            else:
                                logger.info(f"   [실패] {date_text} | {title_text[:20]}... | PDF: X")
                                
                        except Exception as e:
                            logger.error(f"상세 페이지 에러: {e}")
                        finally:
                            await new_page.close()

                    except Exception as e:
                        logger.error(f"Row Error: {e}")
                        continue
                
                # 다음 페이지 이동
                next_btn = await page.query_selector(f'a[onclick*="page={current_page+1}"], a:has-text("{current_page+1}")')
                if not next_btn:
                    # "다음" 버튼 시도
                    next_btn = await page.query_selector('a.next, .btn_next')
                
                if next_btn and page_collected > 0:
                    await next_btn.click()
                    await page.wait_for_timeout(3000)
                    current_page += 1
                else:
                    logger.info("마지막 페이지 도달")
                    break
                    
        except Exception as e:
            logger.error(f"Scrape Error: {e}")
            
        return collected_count

    def save_result(self, title, date, pdf_url, page_url):
        """
        결과 저장 (오버라이딩: page_url 제외)
        """
        # 더블 https 체크
        if pdf_url and pdf_url.startswith('https://https://'):
            pdf_url = pdf_url.replace('https://https://', 'https://')

        result = {
            'site': self.site_name,
            'title': title,
            'date': date,
            'pdf_url': pdf_url,
            # 'page_url': page_url, # 제외
            'collected_at': datetime.now().isoformat()
        }
        self.results.append(result)
