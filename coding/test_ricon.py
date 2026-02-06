#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RICTON(대한건설정책연구원) 테스트 스크립트
"""

import asyncio
import sys
import os
import logging
import csv
from datetime import datetime
from playwright.async_api import async_playwright

# 한글 출력 설정
sys.stdout.reconfigure(encoding='utf-8')

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrapers_group3.ricon import RICONScraper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

async def test_ricon_scraper():
    """RICON 스크래퍼 테스트"""
    
    # 테스트 기간 설정 (1개월)
    start_date = "2026-01-01"
    end_date = "2026-01-31"
    
    print(f"\n{'='*80}")
    print(f"🔍 대한건설정책연구원(RICON) 테스트")
    print(f"📅 기간: {start_date} ~ {end_date}")
    print(f"{'='*80}\n")
    
    scraper = RICONScraper(start_date, end_date)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        )
        
        page = await scraper._setup_page(context)
        
        try:
            # 1. 페이지 DOM 디버깅 (선택자 확인용)
            await page.goto(scraper.url, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(3000)
            
            print("\n[디버깅] 페이지 구조 확인:")
            
            # HTML 저장
            content = await page.content()
            with open("debug_ricon.html", "w", encoding="utf-8") as f:
                f.write(content)
            print("💾 HTML 덤프 저장: debug_ricon.html")
            
            # 스크린샷 저장
            await page.screenshot(path="debug_ricon.png", full_page=True)
            print("📸 스크린샷 저장: debug_ricon.png")
            
            # 게시물 리스트 컨테이너 확인
            containers = await page.query_selector_all('.board-list, .list-wrap, table.list')
            for c in containers:
                cls = await c.get_attribute('class')
                print(f"  - 발견된 컨테이너 클래스: {cls}")
                
            # 테스트 실행
            collected = await scraper.scrape(page)
            
            print(f"\n{'='*80}")
            print(f"✅ 수집 완료: {collected}건")
            print(f"{'='*80}\n")
            
            if scraper.results:
                print("📊 수집 결과:\n")
                for i, item in enumerate(scraper.results[:10], 1):
                    print(f"{i}. {item['title'][:50]}")
                    print(f"   날짜: {item['date']}")
                    print(f"   PDF: {item['pdf_url'][:80] if item['pdf_url'] != 'N/A' else '(미추출)'}\n")
                
                # --- [추가] URL 유효성 검증 ---
                if len(scraper.results) > 0:
                    test_item = scraper.results[0]
                    test_url = test_item['pdf_url']
                    referer_url = test_item.get('page_url', scraper.base_url) # 상세 페이지 URL
                    
                    if test_url != "N/A":
                        print(f"\n🧪 URL 유효성 검증 시도: {test_url}")
                        try:
                            # Playwright APIRequest 사용
                            api_request = context.request
                            
                            # 1. 헤더 없이 요청
                            resp = await api_request.get(test_url)
                            ct = resp.headers.get('content-type', '')
                            print(f"   [1차 시도] Status: {resp.status} | Type: {ct}")
                            
                            if resp.status != 200 or 'pdf' not in ct.lower():
                                # 2. Referer 헤더 추가 요청
                                print("   ⚠️ 1차 실패/의심 -> Referer 헤더 추가하여 2차 시도...")
                                resp = await api_request.get(test_url, headers={
                                    "Referer": referer_url,
                                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                                })
                                ct = resp.headers.get('content-type', '')
                                print(f"   [2차 시도] Status: {resp.status} | Type: {ct}")
                                
                                if resp.status == 200 and ('pdf' in ct.lower() or 'octet-stream' in ct.lower()):
                                    print("   ✅ Referer 헤더가 필수입니다! (다운로드 시 Referer를 포함해야 함)")
                                else:
                                    print("   ❌ 다운로드 실패 (URL이 잘못되었거나 세션/권한 문제)")
                            else:
                                print("   ✅ URL 정상 (별도 인증 없이 다운로드 가능)")
                                
                        except Exception as e:
                            print(f"   ❌ 검증 중 에러: {e}")
                # -----------------------------
                
                # CSV 저장
                output_dir = r"D:\Antigravity\coding\output"
                os.makedirs(output_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = os.path.join(output_dir, f"ricon_{timestamp}.csv")
                
                with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=['source', 'title', 'date', 'page_url', 'pdf_url', 'collected_at'])
                    writer.writeheader()
                    writer.writerows(scraper.results)
                print(f"💾 결과 저장: {filepath}")
            else:
                print("⚠️ 수집된 데이터가 없습니다.")
        
        except Exception as e:
            logger.error(f"테스트 실패: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            await context.close()
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_ricon_scraper())
