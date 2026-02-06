import os
import sys
import asyncio
import re
import json
from urllib.parse import urljoin
from datetime import datetime
from playwright.async_api import async_playwright

# 상위 폴더(base.py가 있는 곳)를 sys.path에 추가
cur_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(cur_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from base import AsyncBaseScraper

class CushmanScraper(AsyncBaseScraper):
    def __init__(self, start_date, end_date):
        super().__init__(start_date, end_date, "Cushman & Wakefield")
        self.base_url = "https://www.cushmanwakefield.com"
        # 쿠시먼 한국 리서치 페이지 (인사이트)
        self.target_url = "https://www.cushmanwakefield.com/ko-kr/south-korea/insights?q=&sort=date%20descending"

    async def scrape(self):
        collected_count = 0  # [수정] 초기화 위치 상향 (UnboundLocalError 방지)
        
        async with async_playwright() as p:
            # 봇 탐지 우회를 위한 브라우저 설정
            browser = await p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            # 일반적인 유저 에이전트 사용
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=1,
            )
            
            # 은신 스크립트 (navigator.webdriver 감춤)
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            page = await context.new_page()
            
            print(f"🚀 [쿠시먼] 수집 시작 ({self.start_date} ~ {self.end_date})")
            
            try:
                # 타임아웃 60초
                await page.goto(self.target_url, wait_until='networkidle', timeout=60000)
                
                # 1. 쿠키 동의 팝업 처리 (OneTrust)
                try:
                    accept_btn = await page.wait_for_selector('#onetrust-accept-btn-handler', state='visible', timeout=5000)
                    if accept_btn:
                        print("   🍪 쿠키 동의 팝업 감지. '수락' 클릭.")
                        await accept_btn.click()
                        await page.wait_for_timeout(2000)
                except:
                    pass

                # 강제 대기 (사이트 로딩)
                await page.wait_for_timeout(3000)
                
                # 리스트 아이템 수집을 위한 링크 저장소
                post_links = []
                
                # [수정] 메인 프레임 탐색 및 처리 로직 확보
                # CoveoResultLink 찾기
                try:
                    await page.wait_for_selector('.CoveoResultLink', timeout=10000)
                except:
                    print("   ⚠️ Selector '.CoveoResultLink' 타임아웃. 대체 방법 시도.")

                # 1. 메인 프레임 .CoveoResultLink 확인
                main_items = await page.query_selector_all('.CoveoResultLink')
                if main_items:
                    print(f"   🎉 메인 프레임에서 {len(main_items)}개 발견!")
                    for item in main_items:
                        title = (await item.text_content()).strip()
                        href = await item.get_attribute('href')
                        if href:
                            full_url = urljoin(self.base_url, href)
                            post_links.append({'title': title, 'url': full_url})

                # 2. iframe 탐색 (메인에 없으면)
                if not post_links:
                    print("   ℹ️ 메인 프레임에 결과 없음. iframe 탐색...")
                    for frame in page.frames:
                        f_items = await frame.query_selector_all('.CoveoResultLink')
                        if f_items:
                            print(f"   🎉 iframe({frame.name or frame.url[-20:]})에서 {len(f_items)}개 발견!")
                            for item in f_items:
                                title = (await item.text_content()).strip()
                                href = await item.get_attribute('href')
                                if href:
                                    full_url = href if href.startswith('http') else urljoin(self.base_url, href)
                                    post_links.append({'title': title, 'url': full_url})
                            break # 하나 찾으면 중단

                # 3. Brute Force (최후의 수단: 모든 a 태그)
                if not post_links:
                    print("   🔥 [Fallback] 모든 a 태그 전수 조사 (Brute Force)...")
                    all_anchors = await page.query_selector_all('a')
                    print(f"   → a 태그 총 {len(all_anchors)}개 스캔")
                    
                    keywords = ["report", "outlook", "trend", "insight", "보고서", "전망", "동향", "마켓", "시장"]
                    seen_urls = set()
                    
                    for a in all_anchors:
                        try:
                            # 텍스트가 없거나 숨겨진 요소일 수 있으므로 안전하게
                            txt = (await a.text_content() or "").strip().lower()
                            href = await a.get_attribute('href')
                            
                            if not href or href.startswith('#') or href.startswith('javascript'):
                                continue
                                
                            full_url = href if href.startswith('http') else urljoin(self.base_url, href)
                            
                            # 필터링
                            if full_url in seen_urls: continue
                            
                            is_target = False
                            # 상세 페이지 URL 패턴 확인
                            if "/insights/" in full_url or ".pdf" in full_url:
                                is_target = True
                            # 또는 텍스트에 키워드 포함 (너무 짧은 단어 주의)
                            elif len(txt) > 4 and any(k in txt for k in keywords):
                                is_target = True
                                
                            if is_target:
                                seen_urls.add(full_url)
                                post_links.append({'title': txt or "No Title", 'url': full_url})
                        except:
                            continue

                print(f"   → 최종 수집 대상 링크: {len(post_links)}개")

                # 수집 개수 제한 (테스트용 상위 30개)
                for i, post in enumerate(post_links[:30]):
                    try:
                        await self._scrape_detail(context, post['title'], post['url'])
                        collected_count += 1
                    except Exception as e:
                        print(f"      ⚠️ 상세 처리 중 에러: {e}")
            
            except Exception as e:
                print(f"❌ 큰 에러 발생: {e}")
                import traceback
                traceback.print_exc()

            # 결과 리포트 및 저장
            print(f"\n🏁 [쿠시먼] 전체 수집 완료: 총 {collected_count}건")
            if self.results:
                # [수정] json 모듈 상단 import 했으므로 사용 가능
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_dir = os.path.join(cur_dir, "output")
                os.makedirs(output_dir, exist_ok=True)
                filename = f"cushman_results_{timestamp}.json"
                filepath = os.path.join(output_dir, filename)
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(self.results, f, ensure_ascii=False, indent=4)
                print(f"   💾 결과 저장 완료: {filepath}")
            
            await browser.close()
            return collected_count

    async def _scrape_detail(self, context, title, url):
        page = await context.new_page()
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(1000) # 안정화 대기
            
            body_text = await page.inner_text('body') or ""
            
            # 날짜 추출 (개선된 로직)
            date_text = "0000-00-00"
            
            # 1. 메타 데이터 등에서 찾기 (정규식 확장)
            # YYYY.MM.DD or YYYY-MM-DD
            m1 = re.search(r'20\d{2}[\.-]\s*\d{1,2}[\.-]\s*\d{1,2}', body_text[:3000])
            if m1:
                raw_date = m1.group(0).replace(' ', '')
                parts = re.split(r'[\.-]', raw_date)
                date_text = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
            else:
                # 영문 날짜 (May 12, 2024 등)
                months = "January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
                m2 = re.search(r'(' + months + r')\.?\s+(\d{1,2}),?\s+(20\d{2})', body_text[:3000], re.IGNORECASE)
                if m2:
                    try:
                        m_str, d_str, y_str = m2.groups()
                        # 월 이름(문자열)을 파싱
                        date_str = f"{m_str} {d_str} {y_str}"
                        # %B: Full month name, %b: Abbreviated month name
                        # 두 케이스 모두 처리 위해 시도
                        try:
                            dt = datetime.strptime(date_str, "%B %d %Y")
                        except:
                            dt = datetime.strptime(date_str, "%b %d %Y")
                            
                        date_text = dt.strftime("%Y-%m-%d")
                    except:
                        pass

            # 날짜 필터링
            if not self.is_in_period(date_text):
                # 날짜가 파싱되었는데 범위 밖이면 패스 (0000-00-00은 일단 통과)
                if date_text != "0000-00-00":
                    valid_start = str(self.start_date)
                    valid_end = str(self.end_date)
                    if not (valid_start <= date_text <= valid_end):
                        # print(f"      패스 (날짜 범위 초과): {date_text}")
                        return

            # PDF 다운로드 링크 추출 ([수정] Selector 오류 방지 -> Python 로직으로 처리)
            pdf_url = "N/A"
            
            # 모든 a 태그를 가져와서 Python 레벨에서 검사
            all_links = await page.query_selector_all('a')
            for link in all_links:
                try:
                    href = await link.get_attribute('href')
                    if not href: continue
                    
                    href_lower = href.lower()
                    txt = (await link.text_content() or "").strip().lower()
                    
                    # 조건: href에 .pdf 포함 OR (class/text에 download 등 포함 AND href가 유효)
                    is_pdf = False
                    if ".pdf" in href_lower:
                        is_pdf = True
                    elif "download" in txt or "다운로드" in txt:
                        is_pdf = True
                    
                    if is_pdf:
                        temp_url = urljoin(url, href)
                        # 실제 .pdf 확장자 확인 (다운로드 버튼인데 html 링크일 수도 있음)
                        if ".pdf" in temp_url.lower():
                            pdf_url = temp_url
                            break
                except:
                    continue

            if pdf_url != "N/A":
                print(f"      ✅ 수집: {title[:15]}... ({date_text})")
                self.save_result(title, date_text, pdf_url, url)
            else:
                 # PDF 없어도 날짜가 유효하면 저장 (링크라도 건지게)
                 pass

        except Exception as e:
            # print(f"      ⚠️ 상세 페이지 에러: {e}")
            pass 
        finally:
            await page.close()

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
        print("\n[Cushman & Wakefield 스크래퍼 실행]")
        try:
            start_in = input("시작일 (YYYY-MM-DD) [기본: 2024-01-01]: ").strip()
            start_date = start_in if start_in else "2024-01-01"
            end_in = input("종료일 (YYYY-MM-DD) [기본: 오늘]: ").strip()
            end_date = end_in if end_in else datetime.now().strftime("%Y-%m-%d")
        except KeyboardInterrupt:
            sys.exit(0)

    scraper = CushmanScraper(start_date, end_date)
    asyncio.run(scraper.scrape())
