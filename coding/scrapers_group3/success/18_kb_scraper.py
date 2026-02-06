#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KB금융지주 (KB Research) 스크래퍼
- URL: https://www.kbfg.com/kbresearch/report/reportList.do
- 구조: 목록 -> 상세(선택) -> PDF 다운로드 (JS fn_downFile 호출)
- 특징: fn_downFile('FILE_ID', 'FILE_SN') -> /cmm/fms/FileDown.do?atchFileId=...&fileSn=...
"""

import sys
import os
import asyncio
import logging
import re
from datetime import datetime
from urllib.parse import urljoin
from playwright.async_api import async_playwright

# 상위 폴더 경로 설정 (base.py 호출용)
cur_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(cur_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

try:
    from success.base import AsyncBaseScraper
except ImportError:
    sys.path.append(cur_dir)
    try:
        from base import AsyncBaseScraper
    except ImportError:
        print("❌ base.py를 찾을 수 없습니다.")
        sys.exit(1)

logger = logging.getLogger("KBScraper")

class KBScraper(AsyncBaseScraper):
    def __init__(self, start_date, end_date):
        super().__init__(start_date, end_date, site_name="KB금융지주")
        self.base_url = "https://www.kbfg.com/kbresearch/"
        # 모든 리포트 목록 (파라미터 없이 접근 시 전체 목록 예상)
        self.target_url = "https://www.kbfg.com/kbresearch/report/reportList.do"

    async def _scrape_board(self, page, url):
        await page.goto(url, wait_until='networkidle', timeout=30000)
        
        collected_count = 0
        current_page = 1
        max_pages = 20 # 안전장치
        
        while current_page <= max_pages:
            logger.info(f"   📄 페이지 {current_page} 읽는 중...")
            await page.wait_for_timeout(1000)
            
            # 목록 아이템 추출
            # 보통 div.boardList > ul > li 또는 table tr 구조
            # 구체적인 selector는 페이지 구조에 따라 다르나, title 링크(reportView.do)를 기준으로 찾음
            items = await page.query_selector_all('li:has(a[href*="reportView.do"]), tr:has(a[href*="reportView.do"])')
            
            # 만약 목록에서 감지가 안되면 상세하게 찾기
            if not items:
                # KB Research는 보통 썸네일형(ul.reportList > li) 또는 리스트형임.
                items = await page.query_selector_all('.reportList > li, .boardList tr')
            
            if not items:
                logger.warning("   ⚠️ 목록 아이템을 찾을 수 없습니다.")
                break
                
            logger.info(f"   → 아이템 {len(items)}개 발견")
            
            count_in_page = 0
            
            # 데이터 선행 추출 (DOM 만료 방지)
            extracted_items = []
            for item in items:
                try:
                    # 제목
                    title_elem = await item.query_selector('a[href*="reportView.do"]')
                    if not title_elem: continue
                    title = (await title_elem.text_content()).strip()
                    view_href = await title_elem.get_attribute('href')
                    
                    # 날짜
                    date_elem = await item.query_selector('.date, .regDate, td:nth-child(4), dl dd, dd')
                    date_text = "0000-00-00"
                    if date_elem:
                        txt = (await date_elem.text_content()).strip()
                        m_date = re.search(r'(\d{4})[\.-](\d{2})[\.-](\d{2})', txt)
                        if m_date:
                            date_text = f"{m_date.group(1)}-{m_date.group(2)}-{m_date.group(3)}"
                    else:
                        # 날짜가 텍스트에 섞여 있을 수도 있음
                        raw_txt = (await item.text_content()).strip()
                        m_date = re.search(r'(\d{4})[\.-](\d{2})[\.-](\d{2})', raw_txt)
                        if m_date:
                            date_text = f"{m_date.group(1)}-{m_date.group(2)}-{m_date.group(3)}"
                            
                    # 다운로드 링크(JS)
                    # href 또는 onclick 확인
                    down_btn = await item.query_selector('a[href*="fn_downFile"], a[onclick*="fn_downFile"]')
                    down_js = None
                    if down_btn:
                        href = await down_btn.get_attribute('href')
                        if href and "fn_downFile" in href:
                             down_js = href
                        else:
                             onclick = await down_btn.get_attribute('onclick')
                             if onclick and "fn_downFile" in onclick:
                                 down_js = onclick
                    
                    extracted_items.append({
                        'title': title,
                        'view_href': view_href,
                        'date': date_text,
                        'down_js': down_js
                    })
                except Exception as e:
                    print(f"[DEBUG] Extraction Error: {e}")
                    continue
            
            logger.info(f"   → 추출된 데이터 {len(extracted_items)}건 처리 시작")

            for data in extracted_items:
                try:
                    title = data['title']
                    date_text = data['date']
                    view_href = data['view_href']
                    down_js = data['down_js']
                    full_view_url = urljoin(self.base_url, view_href)
                    
                    # 날짜 체크
                    if date_text != "0000-00-00" and not self.is_in_period(date_text):
                        if date_text < str(self.start_date):
                             pass
                        continue
                        
                    # PDF URL 생성 (목록에서)
                    pdf_url = "N/A"
                    if down_js:
                        pdf_url = self._extract_pdf_url_from_js(down_js)
                    
                    # (B) 상세 페이지 진입 (PDF가 없거나 날짜가 없을 때)
                    # 목록 상태 유지를 위해 새 탭 사용
                    if pdf_url == "N/A" or date_text == "0000-00-00":
                        try:
                            # 새 탭 열기
                            new_page = await page.context.new_page()
                            await new_page.goto(full_view_url, wait_until='networkidle')
                            await new_page.wait_for_timeout(500) # 안정화 대기
                            
                            # 1) 날짜 재확인 (상세)
                            if date_text == "0000-00-00":
                                # dl > dd 패턴이 많음
                                detail_date_elem = await new_page.query_selector('.viewDate, .date, .regDate, dl dd, .boardViewInfo dd')
                                if detail_date_elem:
                                     # 바로 텍스트가 날짜일 수도 있고, "등록일 : 2025..." 형식일 수도 있음
                                     txt = (await detail_date_elem.text_content()).strip()
                                     m = re.search(r'(\d{4})[\.-](\d{2})[\.-](\d{2})', txt)
                                     if m:
                                         date_text = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                                         
                                # 그래도 없으면 전체 텍스트 검색
                                if date_text == "0000-00-00":
                                     full_txt = await new_page.content()
                                     m_all = re.search(r'(\d{4})[\.-](\d{2})[\.-](\d{2})', full_txt)
                                     if m_all:
                                         date_text = f"{m_all.group(1)}-{m_all.group(2)}-{m_all.group(3)}"

                            # 2) PDF 다운로드 버튼 (상세)
                            if pdf_url == "N/A":
                                # 상세 페이지에는 보통 fn_downFile이 있음
                                detail_down_btn = await new_page.query_selector('a[href*="fn_downFile"], a[onclick*="fn_downFile"], button[onclick*="fn_downFile"]')
                                if detail_down_btn:
                                    href = await detail_down_btn.get_attribute('href')
                                    onclick = await detail_down_btn.get_attribute('onclick')
                                    
                                    js_code = href if (href and "fn_downFile" in href) else onclick
                                    if js_code:
                                        pdf_url = self._extract_pdf_url_from_js(js_code)
                            
                        except Exception as e:
                            logger.warning(f"      상세 페이지 에러: {e}")
                        finally:
                            if 'new_page' in locals():
                                await new_page.close()
                    
                    # 최종 저장
                    if pdf_url != "N/A":
                        if date_text == "0000-00-00": date_text = "1900-01-01"
                        
                        logger.info(f"      ✅ 수집: {title[:20]}... ({date_text})")
                        self.save_result(title, date_text, pdf_url, full_view_url)
                        collected_count += 1
                        count_in_page += 1
                    else:
                        logger.debug(f"      PDF 없음 (상세 확인 후): {title}")
                        
                except Exception as e:
                    logger.warning(f"      Process Error: {e}")
            
            # 페이지네이션
            # javascript:fn_linkPage(2) 형식
            # 보통 class="paging" 또는 .pagination
            next_page = current_page + 1
            next_btn = await page.query_selector(f'a[href*="fn_linkPage({next_page})"]')
            
            if next_btn:
                logger.info("   ▶ 다음 페이지 클릭")
                 # JS 호출이므로 click
                await next_btn.click()
                await page.wait_for_load_state('networkidle')
                await page.wait_for_timeout(1000)
                current_page += 1
            else:
                # 10페이지 단위 이동 처리 (Next >)
                # 예: fn_linkPage(11) ...
                # 복잡하므로 일단 숫자 버튼 없으면 종료
                logger.info("   🏁 마지막 페이지 (더 이상 숫자 버튼 없음)")
                break

        return collected_count
        
    def _extract_pdf_url_from_js(self, js_str):
        # javascript: fn_downFile('FILE_000000002001509','0')
        m = re.search(r"fn_downFile\s*\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)", js_str)
        if m:
            atch_file_id = m.group(1)
            file_sn = m.group(2)
            
            # 사용자 로그에 따르면 fileSn=1 로 요청됨.
            # 인자가 '0'일 때 '1'로 변환해야 하는지 확인 필요.
            # 보통 Java 기반 공통 컴포넌트에서 0-index vs 1-index 차이.
            # 일단 안전하게 인자값 그대로 사용하되, 이슈 발생 시 수정.
            if file_sn == '0':
                file_sn = '1' # 로그 기반 추론: 0 -> 1 변환 시도
            
            return f"https://www.kbfg.com/kbresearch/cmm/fms/FileDown.do?atchFileId={atch_file_id}&fileSn={file_sn}"
        return "N/A"

    async def scrape(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            page = await context.new_page()
            
            logger.info(f"🚀 [KB금융지주] 수집 시작 ({self.start_date} ~ {self.end_date})")
            try:
                await self._scrape_board(page, self.target_url)
            except Exception as e:
                logger.error(f"❌ 수집 중 오류: {e}")
            finally:
                await browser.close()

if __name__ == "__main__":
    if sys.platform == 'win32':
        try: sys.stdout.reconfigure(encoding='utf-8')
        except: pass

    import sys
    
    start_date = None
    end_date = None
    
    if len(sys.argv) >= 3:
        start_date = sys.argv[1]
        end_date = sys.argv[2]
    else:
        print("\n[KB금융지주 스크래퍼 실행]")
        try:
            start_in = input("시작일 (YYYY-MM-DD) [Default: 2024-01-01]: ").strip()
            start_date = start_in if start_in else "2024-01-01"
            end_in = input("종료일 (YYYY-MM-DD) [Default: 오늘]: ").strip()
            end_date = end_in if end_in else datetime.now().strftime("%Y-%m-%d")
        except:
            sys.exit(0)

    scraper = KBScraper(start_date, end_date)
    asyncio.run(scraper.scrape())
    
    if scraper.results:
        import json
        out_dir = os.path.join(cur_dir, "output")
        os.makedirs(out_dir, exist_ok=True)
        fpath = os.path.join(out_dir, f"kb_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(scraper.results, f, ensure_ascii=False, indent=2)
        print(f"\n💾 결과 저장: {fpath}")
    else:
        print("\n⚠️ 수집된 데이터 없음")
