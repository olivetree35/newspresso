import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Optional
from playwright.async_api import Page, Response, BrowserContext

# ============================================
# [설정] 로깅 초기화
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class AsyncBaseScraper(ABC):
    """
    연구소 사이트 수집을 위한 Playwright 기반 비동기 추상 기본 클래스
    """
    
    def __init__(self, start_date: str, end_date: str, site_name: str):
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        self.end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        self.site_name = site_name
        self.results: List[Dict] = []
        self.recent_responses: List[str] = []  # PDF URL 캡처용

    # ============================================
    # [추상 메서드] 실제 수집 로직
    # ============================================
    @abstractmethod
    async def scrape(self, page: Page) -> int:
        """
        각 사이트별 수집 로직 구현 (페이지 순회, 항목 추출 등)
        return: 수집된 항목 수
        """
        pass

    # ============================================
    # [네트워크] PDF 응답 감지
    # ============================================
    def _on_response(self, response: Response):
        """
        네트워크 트래픽을 모니터링하여 PDF 파일 URL을 감지합니다.
        """
        try:
            if response.status == 200:
                url = response.url.lower()
                # PDF 또는 파일 다운로드 관련 키워드 (calldownload 추가)
                keywords = ['.pdf', 'download', 'calldownload', 'atchfile', 'filedown', 'file']
                if any(k in url for k in keywords):
                    self.recent_responses.append(response.url)  # 원본 URL 저장 (소문자 변환 전)
                    
                    # 최근 100개까지만 유지
                    if len(self.recent_responses) > 100:
                        self.recent_responses.pop(0)
        except Exception:
            pass

    # ============================================
    # [설정] 브라우저 페이지 초기화
    # ============================================
    async def _setup_page(self, context: BrowserContext) -> Page:
        """
        페이지 생성 및 이벤트 핸들러(네트워크 감지) 등록
        """
        page = await context.new_page()
        page.on("response", self._on_response)
        return page

    # ============================================
    # [유틸] 날짜 범위 확인
    # ============================================
    def is_in_period(self, date_str: str) -> bool:
        """
        입력된 날짜 문자열(YYYY-MM-DD 등)이 설정된 기간 내인지 확인
        """
        try:
             # 다양한 구분자 처리 (., /)
             clean_date = date_str.replace('.', '-').replace('/', '-').strip()
             target_date = datetime.strptime(clean_date, "%Y-%m-%d").date()
             return self.start_date <= target_date <= self.end_date
        except Exception:
             # 날짜 파싱 실패 시 False 반환
             return False

    # ============================================
    # [결과] 데이터 저장 헬퍼
    # ============================================
    def save_result(self, title: str, date: str, pdf_url: str = "", page_url: str = ""):
        """
        수집된 데이터를 내부 리스트에 저장
        """
        self.results.append({
            'source': self.site_name,
            'title': title,
            'date': date,
            'page_url': page_url,
            'pdf_url': pdf_url,
            'collected_at': datetime.now().isoformat()
        })

# ============================================
# 수정 이력
# ============================================
# 수정일시: 2026-02-03 15:35 - web-data-scraper 스킬 규칙 적용 (한글 주석, 섹션 분리)
