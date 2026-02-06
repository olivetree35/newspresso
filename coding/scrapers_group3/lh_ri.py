from .base import AsyncBaseScraper
import logging
from playwright.async_api import Page
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

class LHScraper(AsyncBaseScraper):
    """
    [LH토지주택연구원] 데이터 스크래퍼
    
    수집 대상: LHRI FOCUS (웹진 형태)
    수집 항목: 제목, 날짜, 사이트명, 다운로드 URL
    특이 사항: 목록에는 다운로드 링크가 없고, 상세 페이지로 이동해야 함.
    """

    def __init__(self, start_date: str, end_date: str):
        super().__init__(start_date, end_date, "LH토지주택연구원")
        self.url = "https://lhri.lh.or.kr/web/pblictn/PblictnList.do?menuIdx=516&pblictnCode=LHRI_FOCUS"
        
        # HTML 분석에 따른 셀렉터
        self.item_selector = "ul.journal-list > li"
        self.title_selector = ".textbox .title a"
        self.date_selector = ".infolist .date span:nth-child(2)"

    # ============================================
    # [실행] 페이지 수집 (메인)
    # ============================================
    async def scrape(self, page: Page) -> int:
        collected_count = 0
        try:
            # 1. 목록 페이지 접속
            logger.info(f"[{self.site_name}] 목록 페이지 접속: {self.url}")
            await page.goto(self.url, wait_until='domcontentloaded', timeout=15000)
            await page.wait_for_timeout(2000)
            
            # 2. 목록에서 수집 대상(URL 포함) 추출
            # DOM 참조가 끊기지 않도록 데이터만 먼저 추출합니다.
            targets = []
            items = await page.query_selector_all(self.item_selector)
            
            for item in items:
                # 제목
                title_elem = await item.query_selector(self.title_selector)
                if not title_elem: continue
                title_text = (await title_elem.text_content()).strip()
                
                # 날짜
                date_elem = await item.query_selector(self.date_selector)
                if not date_elem: continue
                date_text = (await date_elem.text_content()).strip()
                
                # 날짜 필터링
                if not self.is_in_period(date_text):
                    continue
                
                # 상세 페이지 진입을 위한 Element Handle 저장? 
                # -> 페이지가 바뀌면 Handle은 무효화됨.
                # -> onclick 이나 href를 추출해야 함.
                # LH HTML: <a href="#" onclick="searchView('456'); return false;">
                # searchView(id) 함수는 form submit을 함. URL로 바로 이동 불가.
                # -> 이 경우 '목록 -> 클릭 -> 뒤로가기'를 반복해야 하는데,
                #    JS Form Submit이라 URL 생성이 까다로움 (PblictnView.do?pblictnId=...)
                
                # 방법: ID 추출해서 URL 직접 구성
                # onclick="searchView('456');"
                try:
                    onclick_attr = await title_elem.get_attribute("onclick")
                    # '456' 추출
                    import re
                    match = re.search(r"searchView\('(\d+)'\)", onclick_attr)
                    if match:
                        p_id = match.group(1)
                        # 상세 URL 직접 구성
                        detail_url = f"https://lhri.lh.or.kr/web/pblictn/PblictnView.do?menuIdx=516&pblictnCode=LHRI_FOCUS&pblictnId={p_id}"
                        targets.append({
                            "title": title_text,
                            "date": date_text,
                            "url": detail_url
                        })
                except Exception as e:
                    logger.debug(f"ID 추출 실패: {e}")

            logger.info(f"[{self.site_name}] 수집 대상 {len(targets)}건 확보. 상세 수집 시작...")

            # 3. 상세 페이지 순회
            for target in targets:
                try:
                    await page.goto(target['url'], wait_until='domcontentloaded', timeout=10000)
                    await page.wait_for_timeout(1000)
                    
                    # PDF 링크 찾기
                    pdf_url = "N/A"
                    try:
                        # 1. 첨부파일 영역 확인 (다운로드, atchFile 등)
                        # LH 상세페이지는 보통 상단이나 하단에 첨부파일 목록이 있음
                        pdf_link = await page.evaluate_handle("""
                            () => {
                                const links = Array.from(document.querySelectorAll('a'));
                                return links.find(a => 
                                    (a.href && (a.href.includes('atchFile') || a.href.includes('.pdf')))
                                );
                            }
                        """)
                        if pdf_link:
                             href = await pdf_link.get_attribute('href')
                             if href:
                                 pdf_url = urljoin(self.url, href)
                    except Exception:
                        pass
                    
                    self.save_result(target['title'], target['date'], pdf_url, target['url'])
                    collected_count += 1
                    logger.info(f"   [완료] {target['title'][:15]}... PDF:{bool(pdf_url!='N/A')}")
                    
                except Exception as e:
                    logger.error(f"상세 수집 실패 ({target['title']}): {e}")

        except Exception as e:
            logger.error(f"스크래핑 치명적 오류: {e}")
            
        return collected_count

# ============================================
# 수정 이력
# ============================================
# 수정일시: 2026-02-03 15:45 - 상세 페이지 진입 로직 개선 (ID 추출 -> URL 구성)
