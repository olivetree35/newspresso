#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Group 3: 동적 웹 수집기 with 네트워크 요청 캡처 (개선됨)
- 실제 PDF 다운로드 URL 추출 (네트워크 응답 모니터링)
- 새 탭 처리 로직 추가
- 사이트명, 제목, 날짜, PDF 다운로드 URL 수집
"""

import asyncio
import importlib
import logging
from datetime import datetime
import re
from urllib.parse import urljoin

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

RESEARCH_SITES = [
    {
        'site_name': 'LH토지주택연구원',
        'url': 'https://lhri.lh.or.kr/web/pblictn/PblictnList.do?menuIdx=516&pblictnCode=LHRI_FOCUS',
        'title_selector': 'td a',
        'date_selector': '.date',
        'pdf_link_selector': 'a[href*="atchFile"], a[href*=".pdf"]',
    },
    {
        'site_name': '한국금융연구원',
        'url': 'https://www.kif.re.kr/kif4/publication/pub_list?mid=20',
        'title_selector': 'h3',
        'date_selector': 'span.date',
        'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    },
    {
        'site_name': 'NICE신용평가',
        'url': 'https://www.nicerating.com/research/researchAll.do',
        'title_selector': 'h3, h4, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="download"], a[href*="pdf"]',
    },
    {
        'site_name': 'KDI',
        'url': 'https://eiec.kdi.re.kr/policy/materialList.do?depth1=A0000&depth2=A0600',
        'title_selector': 'h3',
        'date_selector': 'li span',
        'pdf_link_selector': 'a[href*="file"]',
    },
    {
        'site_name': '대한건설정책연구원',
        'url': 'https://www.ricon.re.kr/board/list.php?group=issue&page=economic_index&cate=9',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="file"], a[href*="pdf"]',
    },
    {
        'site_name': 'LH (인사이트)',
        'url': 'https://lhri.lh.or.kr/web/pblictn/PblictnList.do?menuIdx=346&pblictnCode=LH_INSITE',
        'title_selector': 'td a',
        'date_selector': '.date',
        'pdf_link_selector': 'a[href*="atchFile"], a[href*=".pdf"]',
    },
    {
        'site_name': '하나금융연구소',
        'url': 'https://www.hanaif.re.kr/totalSearch.do?srchNm=KYWD&srchKey=%EB%B6%80%EB%8F%99%EC%82%B0',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    },
    {
        'site_name': '포스코경영연구원',
        'url': 'https://www.posri.re.kr/kor/bbs/report_list.do?mmcd=2402221432440016120&cate=2403071010350015910',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a, button',
    },
    {
        'site_name': '주택금융연구원',
        'url': 'https://researcher.hf.go.kr/researcher/sub02/sub02_05.do',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="file"], a[href*="pdf"]',
    },
    {
        'site_name': '서울연구원',
        'url': 'https://www.si.re.kr/bbs/list.do?key=2024100039',
        'title_selector': 'h3',
        'date_selector': '.date',
        'pdf_link_selector': 'a[href*="file"]',
    },
    {
        'site_name': '국토연구원 (라이브러리)',
        'url': 'https://www.krihs.re.kr/krihsLibraryArticle/articleList.es?mid=a10103010000&pub_kind=1',
        'title_selector': 'td a',
        'date_selector': 'td:nth-child(3)',
        'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    },
    {
        'site_name': '국토연구원 (보드)',
        'url': 'https://www.krihs.re.kr/board.es?mid=a10607000000&bid=0008',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    },
    {
        'site_name': 'LG경영연구원',
        'url': 'https://www.lgbr.co.kr/economy/list.do',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    },
    {
        'site_name': '한국건설산업연구원 (시장전망)',
        'url': 'https://www.cerik.re.kr/material/prospect',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    },
    {
        'site_name': '한국건설산업연구원 (동향브리핑)',
        'url': 'https://www.cerik.re.kr/report/briefing#/',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    },
    {
        'site_name': '현대경제연구원',
        'url': 'https://www.hri.co.kr/kor/report/report.html?mode=1',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    },
    {
        'site_name': 'KDI (토픽)',
        'url': 'https://www.kdi.re.kr/research/topicList?cd=A',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    },
    {
        'site_name': '하나금융연구소 (보드)',
        'url': 'https://www.hanaif.re.kr/boardList.do?menuId=MN2000&tabMenuId=MN2100',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    },
    {
        'site_name': '우리금융연구소',
        'url': 'https://www.wfri.re.kr/ko/web/research_report/research_report.php?search_type=list',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    },
    {
        'site_name': '대신증권',
        'url': 'https://money2.daishin.com/E5/ResearchCenter/Work/DW_ResearchReits.aspx?m=10904&p=11112&v=11661',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    },
    {
        'site_name': 'KB금융지주',
        'url': 'https://www.kbfg.com/kbresearch/report/reportList.do',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    },
    {
        'site_name': 'BKL',
        'url': 'https://www.bkl.co.kr/law/insight/legalDataList?pageIndex=1&whichOne=NEWSLETTER',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    },
    {
        'site_name': '하나금융연구소 (보고서)',
        'url': 'https://www.hanaif.re.kr/boardList.do?menuId=MN1000&tabMenuId=MN1109',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    },
    {
        'site_name': 'IBK경제연구소',
        'url': 'http://research.ibk.co.kr/research/board/economy-news/list',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    },
    {
        'site_name': '캠코',
        'url': 'https://www.kamco.or.kr/portal/bbs/list.do?ptIdx=282&mId=0701030000',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    },
    {
        'site_name': 'CUSHMAN & WAKEFIELD',
        'url': 'https://www.cushmanwakefield.com/ko-kr/south-korea/insights/insight-search',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    },
    {
        'site_name': '교보리얼코',
        'url': 'https://www.kyoborealco.co.kr/insight/marketreport',
        'title_selector': 'h4, h5, .title',
        'date_selector': 'span.date, .date',
        'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    },
    # {
    #     'site_name': 'CBRE',
    #     'url': 'https://www.cbrekorea.com/insights#%EC%9D%B8%EC%82%AC%EC%9D%B4%ED%8A%B8',
    #     'title_selector': 'h4, h5, .title',
    #     'date_selector': 'span.date, .date',
    #     'pdf_link_selector': 'a[href*="pdf"], a[href*="download"]',
    # }
]

class DynamicResearchCollector:
    """동적 웹 수집기 - 네트워크 응답 캡처 (개선됨)"""
    
    def __init__(self, start_date, end_date):
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        self.end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        self.results = []
        self.recent_responses = []
    
    async def collect_from_site(self, page, site_config, browser):
        """단일 사이트에서 데이터 수집 (개선됨)"""
        collected = 0
        
        try:
            def _on_response(response):
                if response.status == 200:
                    url = response.url.lower()
                    if any(keyword in url for keyword in ['.pdf', 'download', 'atchfile', 'filedown', 'file']):
                        self.recent_responses.append(url)
                if len(self.recent_responses) > 200:
                    del self.recent_responses[:50]
            
            page.on("response", _on_response)

            await page.goto(site_config['url'], wait_until='domcontentloaded', timeout=15000)
            await page.wait_for_timeout(2000)
            
            title_elements = await page.query_selector_all(site_config['title_selector'])
            
            if not title_elements:
                logger.warning(f"[{site_config['site_name']}] 항목 없음")
                return collected
            
            for idx, title_elem in enumerate(title_elements[:20]):
                try:
                    title_text = await title_elem.text_content()
                    if not title_text or len(title_text.strip()) < 3:
                        continue
                    
                    date_text = "N/A"
                    try:
                        date_elem = await title_elem.evaluate_handle(f"""
                            el => el.closest('tr, li, article, div[class*="item"]')?.querySelector('{site_config["date_selector"]}')
                        """)
                        if date_elem:
                            date_text = await date_elem.text_content()
                    except Exception as e:
                        logger.debug(f"[{site_config['site_name']}] 날짜 추출 오류: {str(e)[:50]}")
                    
                    pdf_url = "N/A"
                    try:
                        pdf_link = await title_elem.evaluate_handle(f"""
                            el => el.closest('tr, li, article, div[class*="item"]')?.querySelector('{site_config["pdf_link_selector"]}')
                        """)
                        
                        if pdf_link:
                            pdf_href = await pdf_link.get_attribute('href')
                            
                            if pdf_href and ('pdf' in pdf_href.lower() or 'download' in pdf_href.lower()):
                                pdf_url = urljoin(site_config['url'], pdf_href)
                            else:
                                try:
                                    try:
                                        async with browser.context.expect_page(timeout=3000) as event:
                                            await pdf_link.click()
                                            new_tab = await event.value
                                            await new_tab.wait_for_load_state('networkidle', timeout=10000)
                                            pdf_url = new_tab.url
                                            await new_tab.close()
                                    except:
                                        await pdf_link.click()
                                        await page.wait_for_timeout(5000)
                                        
                                        for res_url in reversed(self.recent_responses[-100:]):
                                            if any(keyword in res_url.lower() for keyword in ['.pdf', 'download', 'atchfile', 'filedown', 'file']):
                                                pdf_url = res_url
                                                break
                                except Exception as e:
                                    logger.debug(f"[{site_config['site_name']}] PDF 추출 오류: {str(e)[:50]}")
                    except Exception as e:
                        logger.debug(f"[{site_config['site_name']}] PDF 추출 오류: {str(e)[:50]}")
                    
                    article = {
                        'source': site_config['site_name'],
                        'title': title_text.strip()[:100],
                        'date': date_text.strip() if date_text != "N/A" else "N/A",
                        'page_url': site_config['url'],
                        'pdf_url': pdf_url,
                        'collected_at': datetime.now().isoformat()
                    }
                    self.results.append(article)
                    collected += 1
                
                except Exception as e:
                    logger.debug(f"[{site_config['site_name']}] 항목 {idx} 오류: {str(e)[:50]}")
                    continue
        
        except Exception as e:
            logger.error(f"[{site_config['site_name']}] 수집 오류: {str(e)[:100]}")
        
        return collected

    async def _collect_savills(self, context):
        """Savills 전용 수집 (커스텀 스크래퍼 사용)"""
        try:
            SavillsScraper = importlib.import_module("savills_scraper").SavillsScraper
        except Exception:
            SavillsScraper = importlib.import_module(".savills_scraper", package=__package__).SavillsScraper

        start_date = self.start_date.strftime("%Y-%m-%d")
        end_date = self.end_date.strftime("%Y-%m-%d")
        scraper = SavillsScraper(start_date, end_date)
        page = await scraper._setup_page(context)

        try:
            collected = await scraper.scrape(page)
        finally:
            await page.close()

        if scraper.results:
            self.results.extend(scraper.results)

        return collected
    
    async def _collect_cbre(self, context):
        """CBRE 전용 수집 (목록 -> 상세 페이지 이동 방식)"""
        collected = 0
        logger.info("📄 CBRE 수집 시작...")
        
        try:
            page = await context.new_page()
            # 1. 목록 페이지 접속
            url = "https://www.cbrekorea.com/insights"
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(3000)
            
            # 2. 리포트 상세 페이지 링크 수집
            # /insights/reports/ 패턴을 가진 링크 찾기
            anchors = await page.query_selector_all("a[href*='/insights/reports/']")
            urls = []
            for a in anchors:
                href = await a.get_attribute("href")
                if href and href not in urls:
                    urls.append(urljoin(url, href))
            
            logger.info(f"   🔎 CBRE 리포트 상세 링크 {len(urls)}개 발견")
            
            # 3. 각 상세 페이지 방문하여 수집
            for detail_url in urls[:15]: # 상위 15개만 우선 시도
                try:
                    logger.info(f"      📖 상세 페이지 접속: {detail_url}")
                    await page.goto(detail_url, wait_until='networkidle', timeout=20000)
                    await page.wait_for_timeout(2000)
                    
                    # 제목 추출: h1 또는 .cbre-c-article-header__title
                    title = await page.inner_text("h1")
                    title = title.strip() if title else "No Title"
                    
                    # 날짜 추출: .cbre-c-article-header__date 또는 20XX 패턴
                    date_text = "0000-00-00"
                    body_text = await page.inner_text("body")
                    date_match = re.search(r'20\d{2}[.-]\d{1,2}[.-]\d{1,2}', body_text)
                    if date_match:
                        date_text = date_match.group(0).replace('.', '-')
                    
                    # 다운로드 버튼 찾기 (사용자 힌트)
                    dl_button = await page.query_selector("a.cbre-c-download")
                    if dl_button:
                        pdf_url = await dl_button.get_attribute("href")
                        if pdf_url:
                            pdf_url = urljoin(detail_url, pdf_url.strip())
                            
                            self.results.append({
                                'source': 'CBRE',
                                'title': title,
                                'date': date_text,
                                'page_url': detail_url,
                                'pdf_url': pdf_url,
                                'collected_at': datetime.now().isoformat()
                            })
                            collected += 1
                            logger.info(f"         ✅ 수집 성공: {title[:20]}... ({date_text})")
                        else:
                            logger.warning(f"         ⚠️ 다운로드 링크 href 없음")
                    else:
                        logger.warning(f"         ⚠️ 다운로드 버튼(a.cbre-c-download)을 찾을 수 없음")
                        
                except Exception as e:
                    logger.error(f"         [CBRE] 상세 페이지 오류: {e}")
                    continue

        except Exception as e:
             logger.error(f"   ❌ CBRE 전체 에러: {e}")
        finally:
             await page.close()
             
        return collected
    
    async def collect_all(self):
        async_playwright = importlib.import_module("playwright.async_api").async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
                viewport={'width': 1920, 'height': 1080},
                ignore_https_errors=True
            )
            
            print("\n📚 동적 웹 수집 시작 (네트워크 응답 캡처 - 개선됨)")
            print(f"📅 기간: {self.start_date} ~ {self.end_date}")
            print("=" * 70)
            
            # 1. 일반 사이트 수집 (CBRE 제외됨)
            for site_config in RESEARCH_SITES:
                print(f"📄 {site_config['site_name']} 수집 중...", end=" ", flush=True)
                page = await context.new_page()
                
                collected = await self.collect_from_site(page, site_config, browser)
                print(f"✅ {collected}건")
                
                await page.close()

            # 2. Savills 수집
            print(f"📄 Savills 수집 중...", end=" ", flush=True)
            savills_collected = await self._collect_savills(context)
            print(f"✅ {savills_collected}건")
            
            # 3. CBRE 수집 (New)
            print(f"📄 CBRE 수집 중...", end=" ", flush=True)
            cbre_collected = await self._collect_cbre(context)
            print(f"✅ {cbre_collected}건")
            
            await context.close()
            await browser.close()
        
        print("=" * 70)
        print(f"✅ 수집 완료: 총 {len(self.results)}건\n")
        return self.results

async def main():
    try:
        while True:
            try:
                start_date = input("\n수집 시작일 (YYYY-MM-DD): ").strip()
                datetime.strptime(start_date, "%Y-%m-%d")
                break
            except ValueError:
                print("❌ 날짜 형식이 잘못되었습니다.")
        
        while True:
            try:
                end_date = input("수집 종료일 (YYYY-MM-DD): ").strip()
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                if end_dt >= start_dt:
                    break
                else:
                    print("❌ 종료일이 시작일보다 크거나 같아야 합니다.")
            except ValueError:
                print("❌ 날짜 형식이 잘못되었습니다.")
        
        collector = DynamicResearchCollector(start_date, end_date)
        results = await collector.collect_all()
        
        if results:
            print("\n" + "=" * 130)
            print(f"{'수집 결과 (상위 20건)':<130}")
            print("=" * 130)
            
            for i, article in enumerate(results[:20], 1):
                title_with_url = f"{article['title'][:60]}({article.get('page_url', article['source'])})"
                date_str = article['date'] if article['date'] != "N/A" else "미상"
                site_name = article['source']
                pdf_url = article.get('pdf_url', 'N/A')
                
                if pdf_url == "N/A":
                    pdf_display = "(미추출)"
                else:
                    pdf_display = pdf_url[:60]
                
                print(f"\n#{i}")
                print(f"   제목: {title_with_url}")
                print(f"   날짜: {date_str}")
                print(f"   사이트: {site_name}")
                print(f"   PDF URL: {pdf_display}")
            
            print("\n" + "=" * 130)
            print(f"총 {len(results)}건 수집됨 | 동적 렌더링 + 네트워크 응답 캡처")
            print("=" * 130)
        else:
            print("\n⚠️  해당 기간에 수집된 자료가 없습니다.")
    
    except KeyboardInterrupt:
        print("\n⚠️  사용자가 수집을 중단했습니다.")

if __name__ == "__main__":
    asyncio.run(main())

