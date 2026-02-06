from .base import AsyncBaseScraper
import logging
import re
from playwright.async_api import Page
from urllib.parse import urljoin, unquote

logger = logging.getLogger(__name__)

class KIFScraper(AsyncBaseScraper):
    """
    [한국금융연구원] 데이터 스크래퍼 (Verified Logic Port)
    
    수집 대상: 연구보고서 (KIF)
    수집 항목: 제목, 날짜, PDF 다운로드 URL
    """

    def __init__(self, start_date: str, end_date: str):
        super().__init__(start_date, end_date, "한국금융연구원")
        self.base_url = "https://www.kif.re.kr"
        self.url = "https://www.kif.re.kr/kif4/publication/pub_list?mid=10"
        
    async def scrape(self, page: Page) -> int:
        collected_count = 0
        try:
            logger.info(f"[{self.site_name}] 접속 중: {self.url}")
            await page.goto(self.url, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(3000)
            
            items_data = []
            # 'pub_detail' 링크 수집
            links = await page.query_selector_all('a[href*="pub_detail"]')
            
            for link in links:
                try:
                    href = await link.get_attribute('href')
                    title_text = (await link.text_content()).strip()
                    if not title_text:
                         title_elem = await link.query_selector('.title')
                         if title_elem:
                             title_text = (await title_elem.text_content()).strip()
                    
                    if not title_text or len(title_text) < 3:
                        continue

                    # 제목 정제: "KIF연구보고서" 같은 불필요한 접두어 제거
                    title_text = title_text.replace("KIF연구보고서", "").strip()

                    date_text = "N/A"
                    # 목록에서 날짜 추출 시도
                    try:
                        parent = await link.evaluate_handle('el => el.closest("li")')
                        if parent:
                            date_elem = await parent.query_selector('.date')
                            if date_elem:
                                date_text = (await date_elem.text_content()).strip()
                    except:
                        pass
                    
                    # 제목/날짜 기반 필터링 (간단 체크)
                    # 실제 상세페이지에서 정확한 날짜를 가져오므로 여기선 pass 가능하지만,
                    # 목록에 날짜가 있다면 1차 필터링
                    if date_text != "N/A":
                        if not self.is_in_period(date_text):
                            continue
                            
                            
                    full_url = urljoin(self.url, href)
                    items_data.append({
                        'title': title_text,
                        'date': date_text,
                        'url': full_url
                    })
                    
                except Exception as e:
                    continue

            logger.info(f"[{self.site_name}] 분석 대상 {len(items_data)}건")

            for item in items_data:
                try:
                    await page.goto(item['url'], wait_until='domcontentloaded', timeout=15000)
                    await page.wait_for_timeout(1000)
                    
                    content = await page.content()
                    
                    # 1. 날짜 재확인 (상세페이지 HTML 내 검색)
                    if item['date'] == "N/A":
                        # YYYY-MM-DD or YYYY.MM.DD 패턴 검색
                        date_match = re.search(r'(\d{4}[-.]\d{2}[-.]\d{2})', content)
                        if date_match:
                            d_text = date_match.group(1).replace('.', '-')
                            if self.is_in_period(d_text):
                                item['date'] = d_text
                            else:
                                # 날짜가 범위 밖이면 수집 제외
                                continue
                    
                    # 2. PDF URL 추출 (HTML 소스 내 execDownload 함수 파라미터 검색)
                    pdf_url = "N/A"
                    
                    # KIF 패턴: execDownload(this, '10', '0', '358030', '2026000705CL') 등
                    # 따옴표 유무 등 유연하게 대응
                    match = re.search(r"execDownload\([^,]*,\s*'(\d+)',\s*'(\d+)',\s*'(\d+)',\s*'([^']+)'", content)
                    if not match:
                        match = re.search(r"execDownload\([^,]*,\s*(\d+),\s*(\d+),\s*(\d+),\s*'([^']+)'", content)
                        
                    if match:
                        mid, vid, cno, fcd = match.groups()
                        pdf_url = f"{self.base_url}/kif4/publication/viewer?mid={mid}&vid={vid}&cno={cno}&fcd={fcd}&ft=0"
                    
                    self.save_result(item['title'], item['date'], pdf_url, item['url'])
                    collected_count += 1
                    logger.info(f"   [수집] {item['date']} | {item['title'][:20]}... | PDF: {bool(pdf_url!='N/A')}")
                    
                except Exception as e:
                    logger.error(f"상세 수집 에러: {e}")
                    
        except Exception as e:
            logger.error(f"전체 에러: {e}")
            
        return collected_count
