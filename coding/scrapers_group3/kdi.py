from base import AsyncBaseScraper
import logging
import re
from playwright.async_api import Page
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

class KDIScraper(AsyncBaseScraper):
    """
    [KDI 한국개발연구원] 데이터 스크래퍼
    
    수집 대상: 정책자료실 - 국토개발 분야
    수집 항목: 제목, 날짜, PDF 다운로드 URL
    로직: UI 조작 방식 (주제별 필터 사용)
    """

    def __init__(self, start_date: str, end_date: str):
        super().__init__(start_date, end_date, "한국개발연구원")
        self.base_url = "https://eiec.kdi.re.kr"
        self.main_url = "https://eiec.kdi.re.kr/policy/materialList.do?depth1=M0000&depth2=A&search_txt=&topic=&pg=1&pp=20&type=J&device=pc"
        
    async def scrape(self, page: Page) -> int:
        collected_count = 0
        max_pages = 5
        
        try:
            logger.info(f"[{self.site_name}] 메인 페이지 접속: {self.main_url}")
            await page.goto(self.main_url, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(8000)  # 충분한 대기 시간
            
            # 1. 주제별 필터에서 "국토개발" 선택
            logger.info("주제별 필터에서 '국토개발' 선택 시도...")
            try:
                # 주제 드롭다운 찾기
                subject_select = await page.query_selector('select[name*="topic"], select[name*="subject"], #selectSubject, select#topic')
                
                if subject_select:
                    # "국토개발" 옵션 선택
                    await subject_select.select_option(label="국토개발")
                    logger.info("✅ '국토개발' 선택 완료")
                    await page.wait_for_timeout(1000)
                    
                    # 검색/적용 버튼 클릭
                    search_btn = await page.query_selector('button:has-text("검색"), button:has-text("적용"), input[type="submit"]')
                    if search_btn:
                        await search_btn.click()
                        logger.info("✅ 검색 버튼 클릭 완료")
                        await page.wait_for_timeout(3000)
                else:
                    logger.warning("⚠️ 주제 필터를 찾을 수 없습니다 - 전체 데이터에서 필터링합니다")
            except Exception as e:
                logger.warning(f"⚠️ 주제 필터 선택 실패: {e} - 전체 데이터에서 필터링합니다")
            
            # 2. 페이지네이션 순회
            current_page = 1
            
            while current_page <= max_pages:
                logger.info(f"[{self.site_name}] 페이지 {current_page}/{max_pages} 처리 중...")
                
                # 게시물 목록 추출
                items = await page.query_selector_all('li a[href*="materialView"], tr td a[href*="materialView"], .list-item a[href*="view"]')
                
                if not items:
                    logger.info("더 이상 게시물이 없습니다.")
                    break
                
                logger.info(f"   {len(items)}개 게시물 발견")
                
                # 데이터 수집
                targets = []
                for item in items:
                    try:
                        title = (await item.text_content()).strip()
                        href = await item.get_attribute('href')
                        
                        if not title or len(title) < 3 or not href:
                            continue
                        
                        # 날짜 추출 (부모 요소에서)
                        date_str = "N/A"
                        parent = await item.evaluate_handle('el => el.closest("tr, li, .list-item")')
                        if parent:
                            parent_text = await parent.text_content()
                            # YYYY.MM.DD or YYYY-MM-DD 패턴 찾기
                            date_match = re.search(r'(\d{4}[.\-/]\d{2}[.\-/]\d{2})', parent_text)
                            if date_match:
                                date_str = date_match.group(1).replace('.', '-').replace('/', '-')
                        
                        # 날짜 필터링
                        if date_str != "N/A":
                            if not self.is_in_period(date_str):
                                continue
                        
                        # URL 구성
                        full_url = urljoin(self.base_url, href)
                        
                        targets.append({
                            'title': title,
                            'date': date_str,
                            'url': full_url
                        })
                    except Exception as e:
                        logger.debug(f"항목 파싱 오류: {e}")
                        continue
                
                if not targets:
                    logger.info(f"페이지 {current_page}: 기간 내 항목 없음")
                    break
                
                # 테스트용: 처음 3건만 처리
                targets = targets[:3]
                logger.info(f"페이지 {current_page}: {len(targets)}건 상세 수집 시작 (테스트 모드)")
                
                # 3. 상세 페이지 순회 및 PDF URL 수집
                for idx, t in enumerate(targets, 1):
                    try:
                        logger.info(f"   [{idx}/{len(targets)}] {t['title'][:40]}... 처리 중")
                        
                        # 랜덤 대기 시간 추가 (봇 감지 우회)
                        import random
                        wait_time = random.randint(4000, 7000)  # 4~7초
                        await page.wait_for_timeout(wait_time)
                        
                        # 상세 페이지 이동
                        await page.goto(t['url'], wait_until='domcontentloaded', timeout=20000)
                        await page.wait_for_timeout(2000)
                        
                        # HTML 전체 가져오기 (KIF 방식)
                        content = await page.content()
                        
                        # "정상적인 요청이 아닙니다" 오류 확인
                        if "정상적인 요청이 아닙니다" in content:
                            logger.warning(f"   ⚠️ 접근 차단 - 15~20초 대기 후 재시도")
                            wait_retry = random.randint(15000, 20000)
                            await page.wait_for_timeout(wait_retry)
                            await page.goto(t['url'], wait_until='domcontentloaded', timeout=20000)
                            await page.wait_for_timeout(3000)
                            
                            content = await page.content()
                            if "정상적인 요청이 아닙니다" in content:
                                logger.error(f"   ❌ 재시도 실패 - 건너뜀")
                                continue
                        
                        pdf_url = "N/A"
                        
                        # 4. PDF URL 추출 (KIF 방식: HTML 파싱)
                        # KDI 패턴: callDownload(num, filenum) 또는 onclick="window.location.href='callDownload.do?...'"
                        
                        # 패턴 1: callDownload 함수 호출
                        # 예: onclick="callDownload('276492', '1')" 또는 callDownload(276492, 1)
                        match = re.search(r"callDownload\(['\"]?(\d+)['\"]?,\s*['\"]?(\d+)['\"]?\)", content)
                        
                        if match:
                            num, filenum = match.groups()
                            # dtime은 현재 시간으로 생성
                            import datetime
                            dtime = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                            pdf_url = f"{self.base_url}/policy/callDownload.do?num={num}&filenum={filenum}&dtime={dtime}"
                            logger.info(f"   ✅ [HTML 파싱] callDownload URL 구성: num={num}, filenum={filenum}")
                        
                        # 패턴 2: 직접 링크 (fallback)
                        if pdf_url == "N/A":
                            match2 = re.search(r"callDownload\.do\?([^'\">\s]+)", content)
                            if match2:
                                params = match2.group(1)
                                pdf_url = f"{self.base_url}/policy/callDownload.do?{params}"
                                logger.info(f"   ✅ [HTML 파싱] 직접 링크 발견")
                        
                        # 패턴 3: href 속성에서 직접 추출
                        if pdf_url == "N/A":
                            links = await page.query_selector_all('a[href*="callDownload"]')
                            for link in links:
                                href = await link.get_attribute('href')
                                if href:
                                    pdf_url = urljoin(self.base_url, href)
                                    logger.info(f"   ✅ [HTML 링크] callDownload 발견")
                                    break
                        
                        if pdf_url == "N/A":
                            logger.warning(f"   ⚠️ PDF URL 추출 실패")
                        
                        # 결과 저장
                        self.save_result(t['title'], t['date'], pdf_url, t['url'])
                        collected_count += 1
                        logger.info(f"   [수집] {t['date']} | {t['title'][:30]}... | PDF: {bool(pdf_url!='N/A')}")
                        
                        # 요청 간격 (봇 차단 방지)
                        await page.wait_for_timeout(2000)
                        
                    except Exception as e:
                        logger.error(f"   상세 수집 실패: {str(e)[:100]}")
                
                # 다음 페이지로 이동
                current_page += 1
                
                if current_page <= max_pages:
                    # 페이지네이션 버튼 클릭
                    try:
                        # 목록 페이지로 돌아가기 (pg 파라미터 사용)
                        next_url = f"https://eiec.kdi.re.kr/policy/materialList.do?depth1=M0000&depth2=A&search_txt=&topic=&pg={current_page}&pp=20&type=J&device=pc"
                        await page.goto(next_url, wait_until='domcontentloaded', timeout=20000)
                        await page.wait_for_timeout(2000)
                    except Exception as e:
                        logger.error(f"페이지 이동 실패: {e}")
                        break
                        
        except Exception as e:
            logger.error(f"전체 오류: {e}")
        
        return collected_count

    async def scrape_all(self):
        """통합 수집기 호출용 진입점"""
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            # BaseScraper의 _setup_page 활용 가능하면 좋겠지만, 
            # 여기서는 직접 생성하거나 _setup_page 호출
            page = await self._setup_page(context)
            
            await self.scrape(page)
            
            await browser.close()
