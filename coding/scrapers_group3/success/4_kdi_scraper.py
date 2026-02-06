import sys
import os

# 현재 파일의 디렉토리를 sys.path에 추가 (base 모듈 import 위함)
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

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
            
        # ---------------------------------------------------------
        # 2차 수집: KDI 토픽 (www.kdi.re.kr/research/topicList?cd=A)
        # ---------------------------------------------------------
        try:
            topic_url = "https://www.kdi.re.kr/research/topicList?cd=A"
            logger.info(f"[{self.site_name}] 2차 수집 시작: KDI 토픽 ({topic_url})")
            
            await page.goto(topic_url, wait_until='domcontentloaded', timeout=20000)
            await page.wait_for_timeout(3000)
            
            # 목록 아이템 추출 (.list_type_new > li 등)
            topic_items = await page.query_selector_all('.list_type_new > li, .board_list > li')
            logger.info(f"   [KDI 토픽] 목록 {len(topic_items)}개 발견")
            
            for item in topic_items[:10]: # 상위 10개만 시도
                try:
                    # 제목 및 링크
                    a_tag = await item.query_selector('a.tit, .txt_box > a, dt > a')
                    if not a_tag: continue
                    
                    t_title = await a_tag.text_content()
                    t_href = await a_tag.get_attribute('href')
                    t_full_url = urljoin("https://www.kdi.re.kr", t_href)
                    
                    # 날짜 확인
                    d_tag = await item.query_selector('.date, span.date, .dt')
                    if d_tag:
                        t_date = (await d_tag.text_content()).strip().replace('.', '-')
                        # 기간 체크
                        if not self.is_in_period(t_date):
                            continue
                    else:
                        t_date = "N/A"
                    
                    # 상세 페이지 이동
                    await page.goto(t_full_url, wait_until='domcontentloaded', timeout=15000)
                    await page.wait_for_timeout(1500)
                    
                    # [사용자 요청] 원문 다운로드 버튼 클릭 이벤트 파싱
                    # <button type="button" class="i02" onclick="location.href='/file/download...'">
                    
                    t_pdf_url = "N/A"
                    dw_btn = await page.query_selector('button[onclick*="/file/download"], a[href*="/file/download"]')
                    
                    if dw_btn:
                        # 1. onclick 속성에서 추출
                        onclick_val = await dw_btn.get_attribute('onclick')
                        if onclick_val:
                            # location.href='...' 패턴 추출
                            m = re.search(r"location\.href=['\"]([^'\"]+)['\"]", onclick_val)
                            if m:
                                t_pdf_url = urljoin("https://www.kdi.re.kr", m.group(1))
                        
                        # 2. href 속성에서 추출 (a 태그일 경우)
                        if t_pdf_url == "N/A":
                            href_val = await dw_btn.get_attribute('href')
                            if href_val and "/file/download" in href_val:
                                t_pdf_url = urljoin("https://www.kdi.re.kr", href_val)
                    
                    if t_pdf_url != "N/A":
                         logger.info(f"   ✅ [KDI 토픽] PDF URL 추출 성공: {t_pdf_url}")
                    
                    self.save_result(t_title.strip(), t_date, t_pdf_url, t_full_url)
                    collected_count += 1
                    
                    # 목록으로 복귀 (history back이 빠름)
                    await page.go_back()
                    await page.wait_for_timeout(1000)
                    
                except Exception as e:
                    logger.warning(f"   [KDI 토픽] 아이템 처리 오류: {e}")
                    # 복구를 위해 다시 목록으로 이동 시도
                    if page.url != topic_url:
                        await page.goto(topic_url, wait_until='domcontentloaded')
        
        except Exception as e:
            logger.error(f"[KDI 토픽] 2차 수집 실패: {e}")
        
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

if __name__ == "__main__":
    import sys
    import asyncio
    
    # 윈도우 인코딩 설정
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except:
            pass
    
    start_date = None
    end_date = None
    
    if len(sys.argv) >= 3:
        start_date = sys.argv[1]
        end_date = sys.argv[2]
    else:
        print("\n[KDI 스크래퍼 실행]")
        try:
            start_date = input("수집 시작일 (YYYY-MM-DD): ").strip()
            if not start_date:
                start_date = "2024-01-01" # Default
                
            end_date = input("수집 종료일 (YYYY-MM-DD): ").strip()
            if not end_date:
                import datetime
                end_date = datetime.datetime.now().strftime("%Y-%m-%d")
        except KeyboardInterrupt:
            print("\n취소되었습니다.")
            sys.exit(0)
    
    print(f"\n📅 수집 기간: {start_date} ~ {end_date}")
    
    scraper = KDIScraper(start_date, end_date)
    asyncio.run(scraper.scrape_all())
